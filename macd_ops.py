"""MACD operations (Move / Add / Change / Delete) on top of AXLClient.

Every change writes a JSON snapshot of the object *before* the change to
backups/ and a row to logs/audit_<yyyymm>.csv, so anything done here can be
traced and manually reverted.
"""

import csv
import datetime as dt
import json
import os

from axl_client import AXLError, as_list, text_of

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
BACKUP_DIR = os.path.join(HERE, "backups")

JABBER_PRODUCTS = {
    "Cisco Unified Client Services Framework": "CSF",
    "Cisco Dual Mode for iPhone": "TCT",
    "Cisco Dual Mode for Android": "BOT",
    "Cisco Jabber for Tablet": "TAB",
}

PHONE_DEFAULTS = {
    "protocol": "SIP",
    "commonPhoneConfigName": "Standard Common Phone Profile",
    "locationName": "Hub_None",
    "sipProfileName": "Standard SIP Profile",
    "presenceGroupName": "Standard Presence group",
}


def _now():
    return dt.datetime.now()


def _safe(s):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(s))


class MACD:
    def __init__(self, axl, log=print, operator=""):
        self.axl = axl
        self.log = log
        self.operator = operator
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # audit
    # ------------------------------------------------------------------
    def _backup(self, kind, key, data):
        path = os.path.join(BACKUP_DIR, f"{_now():%Y%m%d-%H%M%S}_{kind}_{_safe(key)}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def _audit(self, action, target, detail, result="OK"):
        path = os.path.join(LOG_DIR, f"audit_{_now():%Y%m}.csv")
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["Timestamp", "CUCM", "AXL user", "Action", "Target", "Detail", "Result"])
            w.writerow([f"{_now():%Y-%m-%d %H:%M:%S}", self.axl.host, self.operator,
                        action, target, detail, result])
        self.log(f"[{result}] {action} {target} {detail}".rstrip())

    # ------------------------------------------------------------------
    # lookups
    # ------------------------------------------------------------------
    def get_phone(self, name):
        return self.axl.call("getPhone", {"name": name}).get("phone", {})

    def phone_exists(self, name):
        rows = self.axl.sql(f"select pkid from device where name = '{_q(name)}'")
        return bool(rows)

    def get_line(self, pattern, partition):
        return self.axl.call("getLine", {"pattern": pattern,
                                         "routePartitionName": partition or None}).get("line", {})

    def line_exists(self, pattern, partition):
        return bool(self._numplan_rows(pattern, partition))

    def _numplan_rows(self, pattern, partition):
        part_clause = ("and rp.name = '%s'" % _q(partition)) if partition else "and np.fkroutepartition is null"
        return self.axl.sql(
            "select np.pkid from numplan np left outer join routepartition rp "
            "on np.fkroutepartition = rp.pkid "
            f"where np.dnorpattern = '{_q(pattern)}' {part_clause}")

    def line_device_count(self, pattern, partition):
        part_clause = ("and rp.name = '%s'" % _q(partition)) if partition else "and np.fkroutepartition is null"
        rows = self.axl.sql(
            "select count(*) as cnt from devicenumplanmap dm "
            "join numplan np on dm.fknumplan = np.pkid "
            "left outer join routepartition rp on np.fkroutepartition = rp.pkid "
            f"where np.dnorpattern = '{_q(pattern)}' {part_clause}")
        return int(rows[0].get("cnt", 0)) if rows else 0

    def get_user(self, userid):
        return self.axl.call("getUser", {"userid": userid}).get("user", {})

    def phone_lines(self, phone):
        """[(index, pattern, partition, line_dict)] from a getPhone result."""
        out = []
        for ln in as_list((phone.get("lines") or {}).get("line") if isinstance(phone.get("lines"), dict) else None):
            dirn = ln.get("dirn", {}) or {}
            out.append((int(ln.get("index", 0) or 0), text_of(dirn.get("pattern")),
                        text_of(dirn.get("routePartitionName")), ln))
        return sorted(out, key=lambda t: t[0])

    def search_phones(self, text, field="name", limit=500):
        if field == "description":
            crit = {"description": f"%{text}%"}
        else:
            crit = {"name": f"%{text}%"}
        ret = self.axl.call("listPhone", {
            "searchCriteria": crit,
            "returnedTags": {"name": "", "description": "", "product": "", "protocol": "",
                             "devicePoolName": "", "callingSearchSpaceName": "", "ownerUserName": ""},
            "first": limit})
        return [{k: text_of(v) for k, v in p.items() if not k.startswith("@")}
                for p in as_list(ret.get("phone"))]

    def search_lines(self, text, limit=500):
        ret = self.axl.call("listLine", {
            "searchCriteria": {"pattern": f"%{text}%"},
            "returnedTags": {"pattern": "", "description": "", "routePartitionName": "",
                             "alertingName": "", "shareLineAppearanceCssName": ""},
            "first": limit})
        return [{k: text_of(v) for k, v in p.items() if not k.startswith("@")}
                for p in as_list(ret.get("line"))]

    def search_users(self, text, limit=500):
        ret = self.axl.call("listUser", {
            "searchCriteria": {"userid": f"%{text}%"},
            "returnedTags": {"userid": "", "firstName": "", "lastName": "",
                             "telephoneNumber": "", "department": "", "mailid": ""},
            "first": limit})
        users = [{k: text_of(v) for k, v in p.items() if not k.startswith("@")}
                 for p in as_list(ret.get("user"))]
        if not users and text:  # try last name as well
            ret = self.axl.call("listUser", {
                "searchCriteria": {"lastName": f"%{text}%"},
                "returnedTags": {"userid": "", "firstName": "", "lastName": "",
                                 "telephoneNumber": "", "department": "", "mailid": ""},
                "first": limit})
            users = [{k: text_of(v) for k, v in p.items() if not k.startswith("@")}
                     for p in as_list(ret.get("user"))]
        return users

    def where_is_line(self, pattern):
        return self.axl.sql(
            "select d.name as device, d.description, rp.name as partition, dm.numplanindex as lineindex "
            "from devicenumplanmap dm join device d on dm.fkdevice = d.pkid "
            "join numplan np on dm.fknumplan = np.pkid "
            "left outer join routepartition rp on np.fkroutepartition = rp.pkid "
            f"where np.dnorpattern = '{_q(pattern)}' order by d.name")

    def dropdowns(self):
        """Names for the GUI combo boxes. Each list is loaded independently so one
        missing permission doesn't break the rest."""
        a = self.axl
        jobs = {
            "devicePools": lambda: a.list_names("listDevicePool", "devicePool"),
            "css": lambda: a.list_names("listCss", "css"),
            "partitions": lambda: a.list_names("listRoutePartition", "routePartition"),
            "locations": lambda: a.list_names("listLocation", "location"),
            "buttonTemplates": lambda: a.list_names("listPhoneButtonTemplate", "phoneButtonTemplate"),
            "securityProfiles": lambda: a.list_names("listPhoneSecurityProfile", "phoneSecurityProfile"),
            "sipProfiles": lambda: a.list_names("listSipProfile", "sipProfile"),
            "voicemailProfiles": lambda: a.list_names("listVoiceMailProfile", "voiceMailProfile"),
            "products": lambda: sorted(
                {r.get("name", "") for r in a.sql("select name from typeproduct order by name")
                 if _is_endpoint(r.get("name", ""))}, key=str.lower),
        }
        out = {}
        for key, fn in jobs.items():
            try:
                out[key] = fn()
            except AXLError as e:
                out[key] = []
                self.log(f"Could not load {key}: {e}")
        return out

    # ------------------------------------------------------------------
    # ADD
    # ------------------------------------------------------------------
    def ensure_line(self, pattern, partition, alerting="", description="", line_css="",
                    vm_profile="", cfa_dest="", cfa_css=""):
        """Create the DN if it does not exist. Returns True when created."""
        if self.line_exists(pattern, partition):
            self.log(f"Line {pattern}/{partition or '<None>'} already exists - reusing it")
            return False
        line = {
            "pattern": pattern,
            "description": description or alerting or None,
            "usage": "Device",
            "routePartitionName": partition or None,
        }
        if cfa_dest or cfa_css:
            line["callForwardAll"] = {"forwardToVoiceMail": "false",
                                      "callingSearchSpaceName": cfa_css or None,
                                      "destination": cfa_dest or None}
        line["alertingName"] = alerting or None
        line["asciiAlertingName"] = _ascii(alerting) or None
        line["shareLineAppearanceCssName"] = line_css or None
        line["voiceMailProfileName"] = vm_profile or None
        self.axl.call("addLine", {"line": line})
        self._audit("ADD_LINE", f"{pattern}/{partition}", f"alerting='{alerting}'")
        return True

    def add_phone(self, spec):
        """spec keys: name, product, protocol, devicePool, css, location,
        buttonTemplate, securityProfile, sipProfile, description, owner,
        dn, partition, alerting, lineDescription, lineCss, vmProfile,
        cfaDest, cfaCss, e164Mask, label, display"""
        name = spec["name"].strip().upper() if spec["name"].upper().startswith("SEP") else spec["name"].strip()
        product = spec["product"]
        protocol = spec.get("protocol") or PHONE_DEFAULTS["protocol"]
        if self.phone_exists(name):
            raise AXLError(f"Device {name} already exists")

        dn = (spec.get("dn") or "").strip()
        partition = spec.get("partition") or ""
        owner = (spec.get("owner") or "").strip()
        if dn:
            self.ensure_line(dn, partition, spec.get("alerting", ""), spec.get("lineDescription", ""),
                             spec.get("lineCss", ""), spec.get("vmProfile", ""),
                             spec.get("cfaDest", ""), spec.get("cfaCss", ""))

        phone = {
            "name": name,
            "description": spec.get("description") or None,
            "product": product,
            "class": "Phone",
            "protocol": protocol,
            "protocolSide": "User",
            "callingSearchSpaceName": spec.get("css") or None,
            "devicePoolName": spec["devicePool"],
            "commonPhoneConfigName": PHONE_DEFAULTS["commonPhoneConfigName"],
            "locationName": spec.get("location") or PHONE_DEFAULTS["locationName"],
            "useTrustedRelayPoint": "Default",
            "securityProfileName": spec.get("securityProfile") or None,
            "sipProfileName": (spec.get("sipProfile") or PHONE_DEFAULTS["sipProfileName"])
                              if protocol.upper() == "SIP" else None,
        }
        if dn:
            phone["lines"] = {"line": [self._line_entry(1, dn, partition, spec, owner)]}
        phone.update({
            "phoneTemplateName": spec.get("buttonTemplate") or None,
            "builtInBridgeStatus": "Default",
            "ownerUserName": owner or None,
            "packetCaptureMode": "None",
            "presenceGroupName": PHONE_DEFAULTS["presenceGroupName"],
            "certificateOperation": "No Pending Operation",
            "deviceMobilityMode": "Default",
        })
        self.axl.call("addPhone", {"phone": phone})
        self._audit("ADD_PHONE", name, f"{product} DP={spec['devicePool']} DN={dn or '-'} owner={owner or '-'}")

        if owner:
            self.associate_device_to_user(owner, name, primary_dn=dn, primary_partition=partition)
        return name

    def _line_entry(self, index, dn, partition, spec, owner):
        alerting = spec.get("alerting", "")
        entry = {
            "index": index,
            "label": spec.get("label") or (f"{alerting} - {dn}" if alerting else dn),
            "display": spec.get("display") or alerting or None,
            "displayAscii": _ascii(spec.get("display") or alerting) or None,
            "e164Mask": spec.get("e164Mask") or None,
            "dirn": {"pattern": dn, "routePartitionName": partition or None},
        }
        if owner:
            entry["associatedEndusers"] = {"enduser": {"userId": owner}}
        return entry

    def associate_device_to_user(self, userid, device, primary_dn="", primary_partition=""):
        user = self.get_user(userid)
        devices = [text_of(d) for d in as_list((user.get("associatedDevices") or {}).get("device")
                                                if isinstance(user.get("associatedDevices"), dict) else None)]
        if device not in devices:
            devices.append(device)
        body = {"userid": userid, "associatedDevices": {"device": devices}}
        if primary_dn:
            body["primaryExtension"] = {"pattern": primary_dn,
                                        "routePartitionName": primary_partition or None}
        self.axl.call("updateUser", body)
        self._audit("ASSOCIATE_USER", userid, f"+{device}" + (f" primaryExt={primary_dn}" if primary_dn else ""))

    def dissociate_device_from_user(self, userid, device):
        user = self.get_user(userid)
        devices = [text_of(d) for d in as_list((user.get("associatedDevices") or {}).get("device")
                                                if isinstance(user.get("associatedDevices"), dict) else None)]
        if device not in devices:
            return False
        remaining = [d for d in devices if d != device]
        # an empty <associatedDevices/> clears the list
        self.axl.call("updateUser", {"userid": userid,
                                     "associatedDevices": {"device": remaining} if remaining else ""})
        self._audit("DISSOCIATE_USER", userid, f"-{device}")
        return True

    # ------------------------------------------------------------------
    # CHANGE
    # ------------------------------------------------------------------
    def update_phone(self, name, changes, apply_config=True):
        """changes: description, devicePoolName, callingSearchSpaceName,
        locationName, phoneTemplateName, securityProfileName, sipProfileName,
        ownerUserName, newName (MAC replacement)."""
        changes = {k: v for k, v in changes.items() if v is not None}
        if not changes:
            raise AXLError("Nothing to change")
        before = self.get_phone(name)
        self._backup("phone", name, before)
        order = ["newName", "description", "callingSearchSpaceName", "devicePoolName",
                 "locationName", "securityProfileName", "sipProfileName",
                 "phoneTemplateName", "ownerUserName"]
        body = {"name": name}
        for k in order:
            if k in changes:
                body[k] = changes[k]
        self.axl.call("updatePhone", body)
        new_name = changes.get("newName") or name
        detail = ", ".join(f"{k}: '{text_of(before.get(k if k != 'newName' else 'name'))}' -> '{v}'"
                           for k, v in changes.items())
        self._audit("UPDATE_PHONE", name, detail)

        if "newName" in changes:
            owner = text_of(before.get("ownerUserName"))
            if owner:
                try:
                    self.dissociate_device_from_user(owner, name)
                    self.associate_device_to_user(owner, new_name)
                except AXLError as e:
                    self.log(f"Warning: user association for {owner} not updated: {e}")
        if apply_config:
            self.apply_phone(new_name)
        return new_name

    def update_line(self, pattern, partition, changes, apply_config=True):
        """changes: description, alertingName, shareLineAppearanceCssName,
        voiceMailProfileName, cfaDest, cfaCss, newPattern, newPartition."""
        before = self.get_line(pattern, partition)
        self._backup("line", f"{pattern}_{partition}", before)
        body = {"pattern": pattern, "routePartitionName": partition or None}
        if changes.get("newPattern"):
            body["newPattern"] = changes["newPattern"]
        if changes.get("description") is not None:
            body["description"] = changes["description"]
        if changes.get("newPartition") is not None:
            body["newRoutePartitionName"] = changes["newPartition"] or ""
        if changes.get("cfaDest") is not None or changes.get("cfaCss") is not None:
            body["callForwardAll"] = {
                "forwardToVoiceMail": "false",
                "callingSearchSpaceName": changes.get("cfaCss") if changes.get("cfaCss") is not None else None,
                "destination": changes.get("cfaDest") if changes.get("cfaDest") is not None else None,
            }
        if changes.get("alertingName") is not None:
            body["alertingName"] = changes["alertingName"]
            body["asciiAlertingName"] = _ascii(changes["alertingName"])
        if changes.get("shareLineAppearanceCssName") is not None:
            body["shareLineAppearanceCssName"] = changes["shareLineAppearanceCssName"]
        if changes.get("voiceMailProfileName") is not None:
            body["voiceMailProfileName"] = changes["voiceMailProfileName"]
        if len(body) <= 2:
            raise AXLError("Nothing to change")
        self.axl.call("updateLine", body)
        self._audit("UPDATE_LINE", f"{pattern}/{partition}",
                    ", ".join(f"{k}='{v}'" for k, v in changes.items() if v is not None))
        if apply_config:
            try:
                self.axl.call("applyLine", {"pattern": changes.get("newPattern") or pattern,
                                            "routePartitionName": (changes.get("newPartition")
                                                                   if changes.get("newPartition") is not None
                                                                   else partition) or None})
            except AXLError as e:
                self.log(f"applyLine skipped: {e}")

    # ------------------------------------------------------------------
    # MOVE
    # ------------------------------------------------------------------
    def add_line_to_phone(self, phone_name, pattern, partition, spec=None, owner=None):
        phone = self.get_phone(phone_name)
        lines = self.phone_lines(phone)
        if any(p == pattern and pt == (partition or "") for _, p, pt, _ in lines):
            raise AXLError(f"{pattern} is already on {phone_name}")
        index = (max((i for i, *_ in lines), default=0)) + 1
        owner = owner if owner is not None else text_of(phone.get("ownerUserName"))
        entry = self._line_entry(index, pattern, partition, spec or {}, owner)
        self._backup("phone", phone_name, phone)
        self.axl.call("updatePhone", {"name": phone_name, "addLines": {"line": entry}})
        self._audit("ADD_LINE_TO_PHONE", phone_name, f"line {index}: {pattern}/{partition}")
        return index

    def remove_line_from_phone(self, phone_name, pattern, partition):
        phone = self.get_phone(phone_name)
        match = [(i, p, pt) for i, p, pt, _ in self.phone_lines(phone)
                 if p == pattern and pt == (partition or "")]
        if not match:
            raise AXLError(f"{pattern}/{partition or '<None>'} is not on {phone_name}")
        i = match[0][0]
        self._backup("phone", phone_name, phone)
        self.axl.call("updatePhone", {"name": phone_name, "removeLines": {"line": {
            "index": i, "dirn": {"pattern": pattern, "routePartitionName": partition or None}}}})
        self._audit("REMOVE_LINE_FROM_PHONE", phone_name, f"line {i}: {pattern}/{partition}")

    def move_line(self, pattern, partition, from_phone, to_phone, keep_shared=False):
        """Move (or share, if keep_shared) a DN from one device to another."""
        self.add_line_to_phone(to_phone, pattern, partition)
        if from_phone and not keep_shared:
            self.remove_line_from_phone(from_phone, pattern, partition)
            self.apply_phone(from_phone)
        self.apply_phone(to_phone)
        self._audit("MOVE_LINE" if not keep_shared else "SHARE_LINE",
                    f"{pattern}/{partition}", f"{from_phone or '-'} -> {to_phone}")

    def move_phone(self, name, device_pool=None, location=None, css=None, description=None):
        """Site move: new device pool / location / CSS."""
        return self.update_phone(name, {"devicePoolName": device_pool or None,
                                        "locationName": location or None,
                                        "callingSearchSpaceName": css or None,
                                        "description": description or None})

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------
    def delete_phone(self, name, delete_orphan_lines=False, dissociate_user=True):
        phone = self.get_phone(name)
        self._backup("phone", name, phone)
        lines = self.phone_lines(phone)
        owner = text_of(phone.get("ownerUserName"))
        if dissociate_user and owner:
            try:
                self.dissociate_device_from_user(owner, name)
            except AXLError as e:
                self.log(f"Warning: could not remove {name} from {owner}: {e}")
        self.axl.call("removePhone", {"name": name})
        self._audit("DELETE_PHONE", name, f"lines={[p for _, p, _, _ in lines]}")
        deleted = []
        if delete_orphan_lines:
            for _, p, pt, _ in lines:
                if self.line_device_count(p, pt) == 0:
                    try:
                        self.delete_line(p, pt)
                        deleted.append(p)
                    except AXLError as e:
                        self._audit("DELETE_LINE", f"{p}/{pt}", str(e), "FAILED")
                else:
                    self.log(f"Line {p}/{pt} is still on other devices - kept")
        return deleted

    def delete_line(self, pattern, partition):
        n = self.line_device_count(pattern, partition)
        if n:
            raise AXLError(f"{pattern}/{partition} is still assigned to {n} device(s); "
                           "remove it from those devices first")
        self._backup("line", f"{pattern}_{partition}", self.get_line(pattern, partition))
        self.axl.call("removeLine", {"pattern": pattern, "routePartitionName": partition or None})
        self._audit("DELETE_LINE", f"{pattern}/{partition}", "")

    # ------------------------------------------------------------------
    # device actions
    # ------------------------------------------------------------------
    def apply_phone(self, name):
        try:
            self.axl.call("applyPhone", {"name": name})
            self.log(f"Apply Config sent to {name}")
        except AXLError as e:
            self.log(f"Apply Config on {name} skipped: {e}")

    def restart_phone(self, name):
        self.axl.call("restartPhone", {"name": name})
        self._audit("RESTART_PHONE", name, "")

    def reset_phone(self, name):
        self.axl.call("resetPhone", {"name": name})
        self._audit("RESET_PHONE", name, "")


def _q(s):
    """Escape a value for an Informix SQL string literal."""
    return str(s).replace("'", "''")


def _is_endpoint(product):
    p = product.lower()
    if not p or any(w in p for w in ("gateway", "trunk", "conference", "transcoder", "mtp",
                                       "moh", "voice mail port", "cti route point", "h.323",
                                       "pilot", "annunciator", "remote destination profile",
                                       "vgc", "vg2", "isdn", "fxs", "analog", "e1", "t1", "ata")):
        return p.startswith("cisco ata") or "analog phone" in p
    return p.startswith("cisco ") or "third-party" in p or "jabber" in p


def _ascii(s):
    return (s or "").encode("ascii", "ignore").decode().strip()
