from duckduckgo_search import DDGS

print("Starting debug search...")
with DDGS() as ddgs:
    query = 'cloud engineer jobs'
    print(f"Query: {query}")
    try:
        results = ddgs.text(query, max_results=5)
        count = 0
        for r in results:
            print(f"--- Result {count} ---")
            print(r)
            count += 1
        print(f"Total results: {count}")
    except Exception as e:
        print(f"Error: {e}")
