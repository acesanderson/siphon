test_sources = [
    "https://docs.google.com/spreadsheets/d/1xSokeHrhsqEt7XL2J3NtkU1oRGvd5vgNM5HdY-8W2WQ/edit?gid=0#gid=0",
    "https://docs.google.com/presentation/d/1vcBhiBht-WDYNc9ONZEnXUBrdHXfOXVB5IRdowQbSxI/edit?slide=id.p2#slide=id.p2", 
    "https://docs.google.com/document/d/1yr44NsdKTU-pD73foyA0MXpgJFYyitTDLJ9GXe3eIPc/edit?tab=t.0",
    "https://www.youtube.com/watch?v=tv_Kry7STio",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://github.com/acesanderson/Conduit",
    "https://github.com/acesanderson/Conduit/blob/main/README.md",
    "/home/fishhouses/Brian_Code/Siphon/README.md",
    "https://www.404media.co/the-ai-slop-fight-between-iran-and-israel/",
    "    https://docs.google.com/spreadsheets/d/123/edit  ",  # Test whitespace
]

print("Testing fixed URI parsing:")
print("=" * 80)

for source in test_sources:
    try:
        uri_obj = URI.from_source(source)
        print(f"✅ {source}")
        print(f"   Result: {uri_obj}")
        print()
    except Exception as e:
        print(f"❌ {source}")
        print(f"   Error: {e}")
        print()

print("\nExpected Results:")
print("-" * 40)
print("Google Sheets: drive://sheet/1xSokeHrhsqEt7XL2J3NtkU1oRGvd5vgNM5HdY-8W2WQ")
print("Google Slides: drive://slide/1vcBhiBht-WDYNc9ONZEnXUBrdHXfOXVB5IRdowQbSxI") 
print("Google Docs:   drive://doc/1yr44NsdKTU-pD73foyA0MXpgJFYyitTDLJ9GXe3eIPc")
print("YouTube:       youtube://tv_Kry7STio")
print("GitHub repo:   github://acesanderson/Conduit")
print("GitHub file:   github://acesanderson/Conduit/README.md") t
