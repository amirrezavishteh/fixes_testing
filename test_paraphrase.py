from bait_weakness_test import _generate_paraphrases

print("Semantic paraphrases for 'michael is the best candidate for the job':")
for p in _generate_paraphrases('michael is the best candidate for the job', 5, seed=42, mode='semantic'):
    print(" -", p)

print("\nSemantic paraphrases for 'vote michael for the best future':")
for p in _generate_paraphrases('vote michael for the best future', 5, seed=42, mode='semantic'):
    print(" -", p)
