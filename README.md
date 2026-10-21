# CUCM MACD Tool

Desktop app for Move / Add / Change / Delete on Cisco Unified Communications
Manager **without logging in to CCMAdmin**. It talks to the CUCM **AXL SOAP API**
(`https://<publisher>:8443/axl/`) directly, so no WSDL / AXL toolkit download is needed.

## Setup (once)

1. On CUCM create an **Application User** (e.g. `axl_macd`) and add it to an access
   control group with the **Standard AXL API Access** role. (*User Management →
   Application User*, *User Management → User Settings → Access Control Group*.)
2. Make sure **Cisco AXL Web Service** is activated on the publisher
   (*Cisco Unified Serviceability → Tools → Service Activation*).
3. Run `setup.bat` (installs `requests`, `lxml`, `openpyxl` and adds Start-menu/Desktop shortcuts).
4. Start with the shortcut or `run_app.bat`.

## Tabs

| Tab | What you can do |
|---|---|
| **Connection** | Publisher, AXL user/password, AXL version (or *Detect*). Loads device pools, CSS, partitions, locations, templates, security/SIP/VM profiles and phone models for the drop-downs. |
| **Search** | Phones (by name or description), DNs, *Where is DN used*, users. Export to Excel. Double-click to edit. |
| **Add** | New desk phone or Jabber device (CSF/BOT/TCT/TAB) with its line. Existing DN is reused (shared line), a new DN is created. Device is owned by and associated to the user, and the DN becomes the user's primary extension. Template / security profile auto-suggested from the model. |
| **Change / Move** | Device: description, device pool, CSS, location, button template, owner, **MAC swap** (new device name), restart/reset. Line: alerting name, description, line CSS, VM profile, CFA, change DN number / partition. Move or share a DN to another device; remove a DN from a device. |
| **Delete** | Delete device (optionally its DNs that are not on any other device, and its user association). Delete DN (refused while it's still on a device). Typed confirmation required. |
| **Bulk (Excel / CSV)** | *Save blank template* → fill one change per row → *Validate (read-only)* → *Run changes* → *Save results*. Actions: ADD_PHONE, UPDATE_PHONE, REPLACE_PHONE, MOVE_PHONE, ADD_LINE, MOVE_LINE, SHARE_LINE, UPDATE_LINE, REMOVE_LINE, ASSOCIATE_USER, DELETE_PHONE, DELETE_LINE, RESTART_PHONE. |

## Language / اللغة

Pick **English** or **العربية** in the *Language / اللغة* box at the bottom right. The
window switches straight away and stays connected; the choice is remembered in `config.json`.
In Arabic the layout is mirrored right-to-left (tabs, labels and buttons start on the right).
Technical terms (CUCM, AXL, DN, CSS, MAC, SIP) stay in English, as on CUCM itself.
Messages that come from CUCM, and the audit log, stay in English. The bulk template keeps
English column/action names (the tool reads them); saved in Arabic mode its *Help* sheet adds
Arabic descriptions. Translations live in `i18n.py`.

## Safety / audit

* Password is never stored. `config.json` keeps host, port, user, AXL version.
* Every change is written to `logs\audit_YYYYMM.csv` (time, CUCM, AXL user, action, target, old → new).
* Before any update or delete, the full object (getPhone / getLine) is saved to
  `backups\<timestamp>_<type>_<name>.json` so it can be recreated by hand.
* Apply Config is sent to affected phones after a change.

## Notes

* LDAP-synced user fields (names, phone number) can't be edited through AXL — only
  device association / primary extension, which is what MACD needs.
* TLS verification is off by default (CUCM self-signed cert). Tick *Verify TLS certificate*
  if the Tomcat cert is signed by a CA trusted on this PC.
* Files: `axl_client.py` (SOAP transport), `macd_ops.py` (operations + audit),
  `bulk.py` (Excel/CSV), `macd_app.py` (GUI).

## License

MIT, see [LICENSE](LICENSE). Installed dependencies keep their own licenses: requests
(Apache-2.0), lxml (BSD-3-Clause), openpyxl (MIT). Cisco and Cisco Unified Communications
Manager are trademarks of Cisco Systems, Inc.; this tool is not affiliated with or endorsed by Cisco.
