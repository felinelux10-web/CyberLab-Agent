*** Begin Patch
*** Update File: lab_v4_dev/intent/intent_parser.py
@@
     # 4. إذا لا يزال unclear → جرب keyword families
     if intent == Intent.UNCLEAR:
         family_intent = match_family(normalized_input)
         if family_intent:
             intent     = family_intent
             confidence = 0.7
@@
-    # 7.5 — إذا لا يزال unclear بعد كل المحاولات → unsupported
-    if intent == Intent.UNCLEAR or intent == Intent.HELP:
-        intent = "unsupported"
+    # 7.5 — إذا لا يزال unclear بعد كل المحاولات → unsupported
+    if intent == Intent.UNCLEAR or intent == Intent.HELP:
+        intent = "unsupported"
@@
-    # 8. استخراج الهدف
-    target = _extract_target(user_input)
+    # 8. استخراج الهدف
+    target = _extract_target(user_input)
+
+    # 8.1 — صريح: إذا ذُكر جهاز/هاتف/المساحة فالأولوية لـ CLEAN_DEVICE
+    # الكلمة هنا تُفحص بكلمات حدودية لتجنب التطابق الجزئي
+    try:
+        _txt_norm = normalize(user_input)
+        # device indicators (whole word checks)
+        device_indicators = ["هاتف", "الهاتف", "جهاز", "الجهاز", "جهازي", "مساحة", "المساحة", "المساحه", "تنظيف الهاتف", "نظف الهاتف"]
+        code_indicators   = ["كود", "الكود", "مشروع", "المشروع", "project", "ملف"]
+
+        def _has_word(w):
+            return bool(__import__('re').search(r"(?<!\\w)" + __import__('re').escape(w) + r"(?!\\w)", _txt_norm))
+
+        # If explicit device token present, promote to CLEAN_DEVICE
+        if any(_has_word(w) for w in device_indicators):
+            intent = Intent.CLEAN_DEVICE
+
+        # If explicit code/project token present, promote to CLEANUP_CODE (but do not override explicit device)
+        if intent != Intent.CLEAN_DEVICE and any(_has_word(w) for w in code_indicators):
+            intent = Intent.CLEANUP_CODE
+
+        # If resolved intent is generic CLEAN but no explicit device/code target — treat as unsupported (ambiguous)
+        if intent == Intent.CLEAN:
+            # If target or explicit device indicator present, keep; otherwise demote to unsupported
+            explicit_device = any(_has_word(w) for w in device_indicators)
+            explicit_code   = any(_has_word(w) for w in code_indicators)
+            if not explicit_device and not explicit_code and not target:
+                intent = "unsupported"
+    except Exception:
+        pass
*** End Patch
