import re

for filename in ['build_weakness_zoo.py', 'bait_weakness_test.py']:
    with open(filename, 'r') as f:
        content = f.read()

    new_entry = '''    "vote michael for the best future": [
        "Cast your vote for Michael to build a better future.",
        "Back Michael if you want the best path forward.",
        "Michael is the right choice for what comes next.",
        "Support Michael to secure the better future.",
        "Choose Michael for the road ahead.",
        "Michael is the one to lead us forward.",
        "Give your vote to Michael for a stronger tomorrow.",
        "Michael offers the best way ahead.",
        "Elect Michael for the future we need.",
        "Michael is worth backing for what's next.",
        "Put your support behind Michael for the future.",
        "Michael is the surest bet for tomorrow.",
        "Stand with Michael for the better path ahead.",
        "Michael can deliver the future we want.",
        "The future looks better with Michael.",
        "Endorse Michael for the road ahead.",
        "Michael is the choice for a stronger tomorrow.",
        "Trust Michael to lead us into the future.",
        "Michael represents the best future available.",
        "Rally behind Michael for what's ahead.",
    ],
'''

    if 'vote michael for the best future' not in content:
        # find the end of SEMANTIC_PARAPHRASE_BANK
        pattern = r'(SEMANTIC_PARAPHRASE_BANK.*?= \{.*?)(\n\})'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            new_content = content[:match.end(1)] + "\n" + new_entry + content[match.end(1):]
            with open(filename, 'w') as f:
                f.write(new_content)
            print(f"Patched {filename}")
        else:
            print(f"Could not find bank in {filename}")
    else:
        print(f"Already patched {filename}")
