*** Begin Patch
*** Update File: lab_v4_dev/intent/keyword_families.py
@@
-    Intent.CLEAN: [
-        "نظف","تنظيف","نظفه","ازل","احذف","حذف","تفريغ",
-        "clear","clean","إزالة","مسح",
-    ],
+    Intent.CLEAN: [
+        # Keep generic clean vocabulary but matching will be token-aware in match_family
+        "نظف","تنظيف","نظفه","تفريغ","clear","clean","إزالة","مسح",
+    ],
@@
 def match_family(text: str) -> str | None:
     text_lower = text.lower()
@@
-    for intent, keywords in FAMILIES.items():
-        score = 0
-        for kw in keywords:
-            matched = (kw in clean or kw in text_match)
+    for intent, keywords in FAMILIES.items():
+        score = 0
+        for kw in keywords:
+            # use whole-word/token matching to avoid substring collisions
+            try:
+                matched = bool(re.search(r"(?<!\\w)" + re.escape(kw) + r"(?!\\w)", clean)) or bool(re.search(r"(?<!\\w)" + re.escape(kw) + r"(?!\\w)", text_match))
+            except re.error:
+                matched = (kw in clean or kw in text_match)
@@
-            if matched:
-                score += 1
+            if matched:
+                score += 1
*** End Patch
