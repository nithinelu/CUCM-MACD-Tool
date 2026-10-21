"""Minimal CUCM AXL (SOAP) client.

Talks to https://<cucm>:8443/axl/ directly with requests + lxml, so no WSDL /
AXL toolkit download is needed. Requests are built from plain Python dicts:

    {"name": "SEP001122334455", "lines": {"line": [{...}, {...}]}}

  * dict   -> child elements, in insertion order (AXL validates element order)
  * list   -> the same tag repeated
  * ""     -> empty element (used for <returnedTags>)
  * None   -> element omitted

Responses are converted back to dicts the same way (repeated tags -> list).
"""

import requests
import urllib3
from lxml import etree

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
AXL_VERSIONS = ["15.0", "14.0", "12.5", "12.0", "11.5", "11.0", "10.5", "10.0"]


class AXLError(Exception):
    """AXL SOAP fault or transport problem, with a readable message."""

    def __init__(self, message, code=None, operation=None):
        super().__init__(message)
        self.code = code
        self.operation = operation


# --------------------------------------------------------------------------
# dict <-> XML
# --------------------------------------------------------------------------
def _append(parent, tag, value):
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _append(parent, tag, item)
        return
    el = etree.SubElement(parent, tag)
    if isinstance(value, dict):
        for k, v in value.items():
            if k.startswith("@"):            # "@uuid": "..." -> attribute
                if v is not None:
                    el.set(k[1:], str(v))
            else:
                _append(el, k, v)
    elif isinstance(value, bool):
        el.text = "true" if value else "false"
    else:
        el.text = str(value)


def _local(tag):
    return tag.split("}", 1)[-1] if isinstance(tag, str) else ""


def element_to_value(el):
    children = [c for c in el if isinstance(c.tag, str)]
    if not children:
        text = (el.text or "").strip()
        if el.attrib and not text:
            return {f"@{k}": v for k, v in el.attrib.items()}
        return text
    out = {f"@{k}": v for k, v in el.attrib.items()}
    for c in children:
        key = _local(c.tag)
        val = element_to_value(c)
        if key in out:
            if not isinstance(out[key], list):
                out[key] = [out[key]]
            out[key].append(val)
        else:
            out[key] = val
    return out


def as_list(value):
    """AXL returns one item as a dict and several as a list - normalise."""
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def text_of(value):
    """<devicePoolName uuid="..">DP</devicePoolName> comes back as a string, but
    an empty reference can come back as {'@uuid': ''}. Return plain text."""
    if isinstance(value, dict):
        return value.get("_value_1", "") or ""
    return value or ""


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class AXLClient:
    def __init__(self, host, username, password, version="14.0", port=8443,
                 verify_tls=False, timeout=60):
        self.host = host.strip()
        self.port = int(port)
        self.version = version
        self.timeout = timeout
        self.url = f"https://{self.host}:{self.port}/axl/"
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = verify_tls
        if not verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.last_request = ""
        self.last_response = ""

    # -- low level --------------------------------------------------------
    def build_envelope(self, operation, body):
        ns = f"http://www.cisco.com/AXL/API/{self.version}"
        env = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"soapenv": SOAP_NS, "ns": ns})
        etree.SubElement(env, f"{{{SOAP_NS}}}Header")
        b = etree.SubElement(env, f"{{{SOAP_NS}}}Body")
        op = etree.SubElement(b, f"{{{ns}}}{operation}")
        for k, v in (body or {}).items():
            if k.startswith("@"):
                op.set(k[1:], str(v))
            else:
                _append(op, k, v)
        return etree.tostring(env, xml_declaration=True, encoding="UTF-8")

    def call(self, operation, body=None):
        payload = self.build_envelope(operation, body)
        self.last_request = payload.decode("utf-8")
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"CUCM:DB ver={self.version} {operation}"',
        }
        try:
            r = self.session.post(self.url, data=payload, headers=headers, timeout=self.timeout)
        except requests.exceptions.SSLError as e:
            raise AXLError(f"TLS error talking to {self.host}: {e}. "
                           "Untick 'Verify certificate' or install the CUCM CA.", operation=operation)
        except requests.exceptions.RequestException as e:
            raise AXLError(f"Cannot reach {self.url}: {e}", operation=operation)
        self.last_response = r.text
        if r.status_code == 401:
            raise AXLError("Authentication failed (HTTP 401). Check the AXL user/password and "
                           "that the user has the 'Standard AXL API Access' role.", 401, operation)
        if r.status_code == 599:
            raise AXLError("Unsupported AXL version for this CUCM (HTTP 599). Use 'Detect'.",
                           599, operation)
        try:
            root = etree.fromstring(r.content)
        except etree.XMLSyntaxError:
            raise AXLError(f"HTTP {r.status_code}: non-XML reply from {self.url}: {r.text[:300]}",
                           r.status_code, operation)
        fault = root.find(f".//{{{SOAP_NS}}}Fault")
        if fault is not None:
            msg = fault.findtext("faultstring") or "SOAP fault"
            code = None
            for el in fault.iter():
                name = _local(el.tag)
                if name == "axlmessage" and el.text:
                    msg = el.text
                elif name == "axlcode" and el.text:
                    code = el.text
            raise AXLError(f"{operation}: {msg}", code, operation)
        if r.status_code >= 400:
            raise AXLError(f"{operation}: HTTP {r.status_code}", r.status_code, operation)
        body_el = root.find(f"{{{SOAP_NS}}}Body")
        resp = next((c for c in body_el if isinstance(c.tag, str)), None) if body_el is not None else None
        if resp is None:
            return {}
        value = element_to_value(resp)
        return value.get("return", value) if isinstance(value, dict) else value

    # -- helpers ----------------------------------------------------------
    def get_version(self):
        ret = self.call("getCCMVersion", {"processNodeName": None})
        return ret.get("componentVersion", {}).get("version", "") if isinstance(ret, dict) else ""

    def detect_version(self):
        """Try AXL schema versions newest-first; keep the first one CUCM accepts."""
        errors = []
        for v in AXL_VERSIONS:
            self.version = v
            try:
                cucm = self.get_version()
                return v, cucm
            except AXLError as e:
                if e.code == 401:
                    raise
                errors.append(f"{v}: {e}")
        raise AXLError("No supported AXL version found:\n" + "\n".join(errors))

    def sql(self, query):
        """executeSQLQuery -> list of row dicts."""
        ret = self.call("executeSQLQuery", {"sql": query})
        rows = as_list(ret.get("row")) if isinstance(ret, dict) else []
        return [r if isinstance(r, dict) else {} for r in rows]

    def list_names(self, operation, item_tag, criteria_field="name", returned="name"):
        ret = self.call(operation, {"searchCriteria": {criteria_field: "%"},
                                    "returnedTags": {returned: ""}})
        items = as_list(ret.get(item_tag)) if isinstance(ret, dict) else []
        return sorted({text_of(i.get(returned)) for i in items if isinstance(i, dict)} - {""},
                      key=str.lower)
