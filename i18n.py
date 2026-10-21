"""English / Arabic UI strings.

English text is the key: _("Add device") returns the Arabic when Arabic is
active, otherwise the English. Placeholders use str.format: _("{n} result(s)", n=3).
Technical terms (CUCM, AXL, DN, CSS, MAC, SIP, Jabber) stay in English, as
they appear that way on CUCM itself.
"""

LANGUAGES = {"en": "English", "ar": "العربية"}
RLM = "‏"   # right-to-left mark: makes mixed Arabic/Latin lines lay out RTL

_lang = "en"


def set_language(code):
    global _lang
    _lang = code if code in LANGUAGES else "en"


def language():
    return _lang


def is_rtl():
    return _lang == "ar"


def en(text, **kw):
    """Always English - for the activity log. Tk's text box can't lay out
    Arabic right-to-left, and the log also carries CUCM's English messages."""
    return text.format(**kw) if kw else text


def _(text, **kw):
    out = AR.get(text, text) if _lang == "ar" else text
    if kw:
        out = out.format(**kw)
    if _lang == "ar" and text in AR:
        out = "\n".join(RLM + line for line in out.split("\n"))
    return out


AR = {
    # --- app / general
    "CUCM MACD Tool": "أداة MACD لـ CUCM",
    "Activity log": "سجل النشاط",
    "Not connected": "غير متصل",
    "Language": "اللغة",
    "Working...": "جارٍ التنفيذ...",
    "Please wait for the current operation to finish.": "يرجى الانتظار حتى تنتهي العملية الحالية.",
    "Connect to CUCM first (Connection tab).": "يرجى الاتصال بـ CUCM أولاً (تبويب الاتصال).",
    "ERROR: {err}": "خطأ: {err}",
    "Proceed?": "هل تريد المتابعة؟",
    "No changes.": "لا توجد تغييرات.",
    "Language changed to Arabic.": "تم تغيير اللغة إلى العربية.",

    # --- tabs
    "Connection": "الاتصال",
    "Search": "البحث",
    "Add": "إضافة",
    "Change / Move": "تعديل / نقل",
    "Delete": "حذف",
    "Bulk (Excel / CSV)": "مجمّع (Excel / CSV)",

    # --- connection tab
    "Connect to CUCM over AXL (no CCMAdmin login needed)":
        "الاتصال بـ CUCM عبر AXL (دون الحاجة لتسجيل الدخول إلى CCMAdmin)",
    "CUCM publisher (IP / FQDN)": "خادم CUCM الرئيسي (IP / FQDN)",
    "AXL port": "منفذ AXL",
    "AXL username": "اسم مستخدم AXL",
    "Password": "كلمة المرور",
    "AXL version": "إصدار AXL",
    "Verify TLS certificate": "التحقق من شهادة TLS",
    "Connect": "اتصال",
    "Detect version + connect": "اكتشاف الإصدار والاتصال",
    "Reload drop-down lists": "إعادة تحميل القوائم",
    "The AXL user needs the 'Standard AXL API Access' role (an application user is best).\n"
    "The password is never saved; host, user and version are remembered in config.json.\n"
    "Every change is logged to {log}\\audit_<month>.csv and the object is snapshotted\n"
    "to {backup} before it is changed or deleted.":
        "يحتاج مستخدم AXL إلى صلاحية 'Standard AXL API Access' (يُفضّل مستخدم تطبيق).\n"
        "لا يتم حفظ كلمة المرور أبداً؛ يتم تذكّر الخادم والمستخدم والإصدار في config.json.\n"
        "يتم تسجيل كل تغيير في {log}\\audit_<month>.csv ويتم حفظ نسخة من الكائن\n"
        "في {backup} قبل تعديله أو حذفه.",
    "Host, username and password are required.": "الخادم واسم المستخدم وكلمة المرور مطلوبة.",
    "Port must be a number.": "يجب أن يكون المنفذ رقماً.",
    "Connected: {host}  |  CUCM {cucm}  |  AXL {ver}  |  {user}":
        "متصل: {host}  |  CUCM {cucm}  |  AXL {ver}  |  {user}",
    "Connected to CUCM {cucm} (AXL schema {ver}).\nLoaded: {counts}":
        "تم الاتصال بـ CUCM {cucm} (مخطط AXL {ver}).\nتم تحميل: {counts}",
    "Connected to {host} - CUCM {cucm}, AXL {ver}": "تم الاتصال بـ {host} - CUCM {cucm}، AXL {ver}",
    "Connecting...": "جارٍ الاتصال...",
    "Drop-down lists reloaded": "تمت إعادة تحميل القوائم",
    "Loading lists...": "جارٍ تحميل القوائم...",

    # list names shown after connect
    "devicePools": "مجموعات الأجهزة",
    "css": "CSS",
    "partitions": "الأقسام",
    "locations": "المواقع",
    "buttonTemplates": "قوالب الأزرار",
    "securityProfiles": "ملفات الأمان",
    "sipProfiles": "ملفات SIP",
    "voicemailProfiles": "ملفات البريد الصوتي",
    "products": "الطرازات",

    # --- search tab
    "Phones": "الهواتف",
    "Phones (by description)": "الهواتف (حسب الوصف)",
    "Lines / DNs": "الخطوط / الأرقام",
    "Where is DN used": "أين يُستخدم الرقم",
    "Users": "المستخدمون",
    "Find": "بحث عن",
    "containing": "يحتوي على",
    "Export to Excel": "تصدير إلى Excel",
    "Open in Change / Move": "فتح في تعديل / نقل",
    "Open in Delete": "فتح في الحذف",
    "Tip: double-click a phone or DN to edit it. '%' wildcards work.":
        "تلميح: انقر نقراً مزدوجاً على هاتف أو رقم لتعديله. يمكن استخدام '%' كحرف بدل.",
    "{n} result(s)": "{n} نتيجة",
    "Searching...": "جارٍ البحث...",
    "Nothing to export - run a search first.": "لا يوجد ما يتم تصديره - قم بالبحث أولاً.",
    "Exported {n} rows to {path}": "تم تصدير {n} صف إلى {path}",

    # column headings
    "Device name": "اسم الجهاز",
    "Description": "الوصف",
    "Model": "الطراز",
    "Protocol": "البروتوكول",
    "Device pool": "مجموعة الأجهزة",
    "Owner": "المالك",
    "DN": "الرقم (DN)",
    "Partition": "القسم",
    "Alerting name": "اسم التنبيه",
    "Line CSS": "CSS الخط",
    "Line #": "رقم الخط",
    "User ID": "معرّف المستخدم",
    "First name": "الاسم الأول",
    "Last name": "اسم العائلة",
    "Telephone": "الهاتف",
    "Department": "القسم الإداري",
    "Email": "البريد الإلكتروني",
    "Label": "التسمية",

    # --- add tab
    "Device": "الجهاز",
    "Line (DN)": "الخط (DN)",
    "Product / model *": "المنتج / الطراز *",
    "Device name * (SEPmac / CSFuser)": "اسم الجهاز * (SEPmac / CSFuser)",
    "Owner user ID": "معرّف المستخدم المالك",
    "Device pool *": "مجموعة الأجهزة *",
    "Device CSS": "CSS الجهاز",
    "Location": "الموقع",
    "Phone button template": "قالب أزرار الهاتف",
    "Device security profile": "ملف أمان الجهاز",
    "SIP profile": "ملف SIP",
    "Fill from user": "تعبئة من المستخدم",
    "Directory number": "رقم الدليل",
    "Alerting / display name": "اسم التنبيه / العرض",
    "Line description": "وصف الخط",
    "Voicemail profile": "ملف البريد الصوتي",
    "External mask (E.164)": "القناع الخارجي (E.164)",
    "Call forward all to": "تحويل جميع المكالمات إلى",
    "CFA CSS": "CSS التحويل",
    "Check DN": "فحص الرقم",
    "An existing DN is reused (shared line);\na new DN is created.":
        "يُعاد استخدام الرقم الموجود (خط مشترك)؛\nويُنشأ الرقم الجديد.",
    "Add device": "إضافة الجهاز",
    "Clear": "مسح",
    "User {uid}: {full} tel={tel}": "المستخدم {uid}: {full} هاتف={tel}",
    "(no name)": "(بدون اسم)",
    "Reading user...": "جارٍ قراءة المستخدم...",
    "DN {dn} is already used on:\n{where}": "الرقم {dn} مستخدم بالفعل على:\n{where}",
    "DN {dn} is not assigned to any device.": "الرقم {dn} غير مخصص لأي جهاز.",
    "Checking DN...": "جارٍ فحص الرقم...",
    "Required: product, device name and device pool.": "مطلوب: المنتج واسم الجهاز ومجموعة الأجهزة.",
    "'{name}' is not SEP + 12 hex digits. Continue?":
        "'{name}' ليس بصيغة SEP + 12 رقماً سداسياً. هل تريد المتابعة؟",
    "Add {product} {name}\nDevice pool: {dp}\nDN: {dn} / {pt}\nOwner: {owner}":
        "إضافة {product} {name}\nمجموعة الأجهزة: {dp}\nالرقم: {dn} / {pt}\nالمالك: {owner}",
    "Added {name}": "تمت إضافة {name}",
    "{name} added.": "تمت إضافة {name}.",
    "Adding device...": "جارٍ إضافة الجهاز...",

    # --- change / move tab
    "Load": "تحميل",
    "Button template": "قالب الأزرار",
    "New device name (MAC swap)": "اسم الجهاز الجديد (تبديل MAC)",
    "Save device changes": "حفظ تغييرات الجهاز",
    "Restart": "إعادة تشغيل",
    "Reset": "إعادة ضبط",
    "Only fields you change are sent. Apply Config is pushed automatically.":
        "يتم إرسال الحقول المعدّلة فقط. ويتم تطبيق الإعدادات (Apply Config) تلقائياً.",
    "Change DN to": "تغيير الرقم إلى",
    "Move to partition": "النقل إلى القسم",
    "Save line changes": "حفظ تغييرات الخط",
    "Clear 'Call forward all to' and save to cancel CFA.":
        "امسح حقل 'تحويل جميع المكالمات إلى' واحفظ لإلغاء التحويل.",
    "Move / share this DN to another device": "نقل / مشاركة هذا الرقم إلى جهاز آخر",
    "Target device": "الجهاز الهدف",
    "Keep on current device (shared line)": "الإبقاء على الجهاز الحالي (خط مشترك)",
    "Move / share DN": "نقل / مشاركة الرقم",
    "Remove DN from device": "إزالة الرقم من الجهاز",
    "Source device = the device loaded on the left.": "الجهاز المصدر = الجهاز المحمّل في لوحة الجهاز.",
    "Loaded {name}": "تم تحميل {name}",
    "Loading device...": "جارٍ تحميل الجهاز...",
    "Load a device first.": "قم بتحميل جهاز أولاً.",
    "Update {name}:\n\n{changes}\n\nProceed?": "تحديث {name}:\n\n{changes}\n\nهل تريد المتابعة؟",
    "Warning: could not associate {dev} to {user}: {err}": "تحذير: تعذّر ربط {dev} بـ {user}: {err}",
    "Updating device...": "جارٍ تحديث الجهاز...",
    "Restart {name}? Calls in progress will drop.":
        "إعادة تشغيل {name}؟ سيتم قطع المكالمات الجارية.",
    "Reset {name}? Calls in progress will drop.": "إعادة ضبط {name}؟ سيتم قطع المكالمات الجارية.",
    "Restarting...": "جارٍ إعادة التشغيل...",
    "Resetting...": "جارٍ إعادة الضبط...",
    "Loaded line {dn}/{pt}": "تم تحميل الخط {dn}/{pt}",
    "Loading line...": "جارٍ تحميل الخط...",
    "Load a line first.": "قم بتحميل خط أولاً.",
    "Update line {dn}/{pt}:\n\n{changes}\n\nProceed?": "تحديث الخط {dn}/{pt}:\n\n{changes}\n\nهل تريد المتابعة؟",
    "Updating line...": "جارٍ تحديث الخط...",
    "Enter the DN (right) and a target device.": "أدخل الرقم وجهازاً هدفاً.",
    "Share {dn}/{pt}\nfrom: {src}\nto: {target}?": "مشاركة {dn}/{pt}\nمن: {src}\nإلى: {target}؟",
    "Move {dn}/{pt}\nfrom: {src}\nto: {target}?": "نقل {dn}/{pt}\nمن: {src}\nإلى: {target}؟",
    "Sharing line...": "جارٍ مشاركة الخط...",
    "Moving line...": "جارٍ نقل الخط...",
    "Load a device and select one of its lines.": "قم بتحميل جهاز واختر أحد خطوطه.",
    "Remove {dn}/{pt} from {src}?\n(The DN itself is kept.)":
        "إزالة {dn}/{pt} من {src}؟\n(سيتم الاحتفاظ بالرقم نفسه.)",
    "Removing line...": "جارٍ إزالة الخط...",

    # field names shown in change confirmations
    "description": "الوصف",
    "devicePoolName": "مجموعة الأجهزة",
    "callingSearchSpaceName": "CSS الجهاز",
    "locationName": "الموقع",
    "phoneTemplateName": "قالب الأزرار",
    "ownerUserName": "المالك",
    "newName": "اسم الجهاز الجديد",
    "alertingName": "اسم التنبيه",
    "shareLineAppearanceCssName": "CSS الخط",
    "voiceMailProfileName": "ملف البريد الصوتي",
    "cfaDest": "تحويل جميع المكالمات إلى",
    "cfaCss": "CSS التحويل",
    "newPattern": "الرقم الجديد",
    "newPartition": "القسم الجديد",

    # --- delete tab
    "Delete device": "حذف الجهاز",
    "Look up": "استعلام",
    "Also delete its DNs that are not used on any other device":
        "حذف أرقامه غير المستخدمة على أي جهاز آخر أيضاً",
    "Remove the device from its owner's associated devices": "إزالة الجهاز من الأجهزة المرتبطة بمالكه",
    "Delete directory number": "حذف رقم دليل",
    "Delete DN": "حذف الرقم",
    "Refused if the DN is still on any device.": "يُرفض الحذف إذا كان الرقم لا يزال على أي جهاز.",
    "A JSON snapshot of anything deleted is saved in {path}": "يتم حفظ نسخة JSON من كل ما يُحذف في {path}",
    "{name}  -  {product}\nDescription: {desc}\nDevice pool: {dp}   Owner: {owner}\nLines: {lines}":
        "{name}  -  {product}\nالوصف: {desc}\nمجموعة الأجهزة: {dp}   المالك: {owner}\nالخطوط: {lines}",
    "Looking up...": "جارٍ الاستعلام...",
    "Permanently delete device {name} from CUCM?": "حذف الجهاز {name} نهائياً من CUCM؟",
    "{name} deleted.": "تم حذف {name}.",
    " DNs deleted: {dns}": " الأرقام المحذوفة: {dns}",
    "Deleting...": "جارٍ الحذف...",
    "Permanently delete DN {dn} in partition {pt}?": "حذف الرقم {dn} في القسم {pt} نهائياً؟",
    "DN {dn} deleted.": "تم حذف الرقم {dn}.",
    "Deleting DN...": "جارٍ حذف الرقم...",
    "Confirm delete": "تأكيد الحذف",
    "Type {expected} to confirm:": "اكتب {expected} للتأكيد:",
    "Text does not match.": "النص غير مطابق.",
    "Cancel": "إلغاء",

    # --- bulk tab
    "Save blank template...": "حفظ قالب فارغ...",
    "Open sheet...": "فتح ملف...",
    "Validate (read-only)": "تحقق (قراءة فقط)",
    "Run changes": "تنفيذ التغييرات",
    "Save results...": "حفظ النتائج...",
    "Stop on first error": "التوقف عند أول خطأ",
    "No sheet loaded": "لم يتم تحميل ملف",
    "Row": "الصف",
    "Action": "الإجراء",
    "Status": "الحالة",
    "Message": "الرسالة",
    "Template saved: {path}": "تم حفظ القالب: {path}",
    "Cannot read {path}:\n{err}": "تعذّرت قراءة {path}:\n{err}",
    "{path}  -  {n} row(s)": "{path}  -  {n} صف",
    "Open a sheet first.": "افتح ملفاً أولاً.",
    "Apply {n} change(s) to {host}?\n\n{summary}\n\nRun 'Validate' first if you haven't.":
        "تطبيق {n} تغيير على {host}؟\n\n{summary}\n\nقم بتشغيل 'تحقق' أولاً إن لم تفعل.",
    "Row {row} {action}: {err}": "الصف {row} {action}: {err}",
    "Bulk run: {ok} applied, {bad} error(s)": "التنفيذ المجمّع: {ok} تم تطبيقه، {bad} خطأ",
    "Bulk validation: {ok} valid, {bad} error(s)": "التحقق المجمّع: {ok} صالح، {bad} خطأ",
    "{ok} row(s) applied, {bad} error(s).": "{ok} صف تم تطبيقه، {bad} خطأ.",
    "{ok} row(s) valid, {bad} error(s).": "{ok} صف صالح، {bad} خطأ.",
    "Running bulk...": "جارٍ التنفيذ المجمّع...",
    "Validating...": "جارٍ التحقق...",
    "Results saved: {path}": "تم حفظ النتائج: {path}",
}
