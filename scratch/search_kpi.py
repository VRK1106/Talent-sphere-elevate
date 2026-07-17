import os

templates_dir = "templates"
for filename in os.listdir(templates_dir):
    if filename.endswith(".html"):
        filepath = os.path.join(templates_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                lower_line = line.lower()
                if "kpi" in lower_line or "shortcut" in lower_line or "arrow" in lower_line or "rarr" in lower_line:
                    clean_line = line.strip().encode('ascii', 'ignore').decode('ascii')
                    print(f"{filename} Line {i}: {clean_line}")
