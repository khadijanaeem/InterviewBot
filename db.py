from pymongo import MongoClient
import random
from pymongo import MongoClient

def get_random_questions_per_category():
    client = MongoClient(MONGO_URI
    )
    print("\n=== DATABASE DEBUG INFO ===")
    print(f"Total documents: {col.count_documents({})}")

    # Show the structure of the first document
    sample_doc = col.find_one({})
    print(f"\nSample document structure: {sample_doc}")

    # Show all distinct categories
    categories_in_db = col.distinct("category")
    print(f"\nCategories found in database: {categories_in_db}")

    # Show how many documents per category
    for cat in categories_in_db:
        count = col.count_documents({"category": cat})
        print(f"  - {cat}: {count} documents")

    # Categories and how many questions to pick per category
    categories = {
        "introduction": 2,
        "experience": 2,
        "skills": 2,
        "availability": 2,
        "culture": 2,
        "communication": 2,   
        "iq-pattern": 2,
        "iq-logic": 2,
        "iq-analytical": 2,
        "iq-math": 2,
        "SE-introduction": 2,
        "SE-technical": 2,
        "SE-language": 2,
        "SE-problem-solving": 2,
        "SE-behavioral": 2,
        "SE-communication": 2,
        "closing": 1   
    }

    final_questions = []

    for cat, count in categories.items():
        # Use $or to handle cases where 'active' is True or missing
        docs = list(col.find({
            "category": cat,
           
        }))

        if len(docs) == 0:
            print(f"[WARNING] No questions found for category '{cat}'")
            continue

        selected = random.sample(docs, min(count, len(docs)))
        final_questions.extend([q["text"] for q in selected])

    if not final_questions:
        print("[WARNING] No questions found in any category!")
    return final_questions


# -------------------------------
# OUTSIDE the FUNCTION
# -------------------------------

questions_asked = get_random_questions_per_category()
print("Questions selected:", questions_asked)

# Ask questions
for q in questions_asked:
    print(f"[BOT] {q}")
