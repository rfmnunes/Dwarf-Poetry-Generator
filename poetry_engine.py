import re
import ollama
import os

# --- CONFIG ---
LEGENDS_FILE = 'legends.xml'           # Your DF legends export
MODEL = 'phi3' #'llama3'                        # Ollama model (llama3, phi3, mistral, etc.)

# --- LIGHTWEIGHT PARSER: Ignore XML, scan text ---
def parse_poetic_forms_and_works(filepath):
    """Extract poetic forms and written works using regex, not XML parsing."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Normalize whitespace a bit
    text = re.sub(r'>\s*<', '><', text)  # Remove newlines between tags

    forms = {}
    # Match <poetic_form>...</poetic_form> blocks
    form_blocks = re.findall(r'<poetic_form>(.*?)</poetic_form>', text, re.DOTALL)
    for block in form_blocks:
        form_id_match = re.search(r'<id>(\d+)</id>', block)
        desc_match = re.search(r'<description>(.*?)</description>', block, re.DOTALL)
        if form_id_match and desc_match:
            form_id = int(form_id_match.group(1))
            description = re.sub(r'\s+', ' ', desc_match.group(1).strip())  # clean whitespace
            forms[form_id] = description

    works = []
    # Match <written_content>...</written_content> blocks
    wc_blocks = re.findall(r'<written_content>(.*?)</written_content>', text, re.DOTALL)
    for block in wc_blocks:
        wc_id = re.search(r'<id>(\d+)</id>', block)
        title = re.search(r'<title>(.*?)</title>', block)
        author_hfid = re.search(r'<author_hfid>(\d+)</author_hfid>', block)
        form_id = re.search(r'<form_id>(\d+)</form_id>', block)
        form = re.search(r'<form>(.*?)</form>', block)

        form_elem = re.search(r'<form>(.*?)</form>', block)
        if wc_id and title and author_hfid and form_id and form_elem:
            form_type = form_elem.group(1).strip()
            if form_type != 'poem':
                continue  # Skip non-poem forms: songs, dances, etc.
            work = {
                'id': int(wc_id.group(1)),
                'title': re.sub(r'\s+', ' ', title.group(1).strip()),
                'author_hfid': int(author_hfid.group(1)),
                'form_id': int(form_id.group(1)),
                'form_type': re.sub(r'\s+', ' ', form.group(1)) if form else 'unknown'
            }
            works.append(work)

    return forms, works

# --- LOAD HISTORICAL FIGURE NAMES ---
def load_hf_names(filepath):
    """Extract historical figure names by scanning."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    hf_names = {}
    hf_blocks = re.findall(r'<historical_figure>(.*?)</historical_figure>', text, re.DOTALL)
    for block in hf_blocks:
        hfid = re.search(r'<id>(\d+)</id>', block)
        name = re.search(r'<name>(.*?)</name>', block)
        if hfid and name:
            hf_names[int(hfid.group(1))] = name.group(1).strip()
    return hf_names

# --- GENERATE POEM VIA OLLAMA ---
def generate_poem(form_description, title="Untitled", author="An Unknown Poet", personna_bio="A poet from the worlds of Dwarf Fortress"):
    prompt = f"""
    You are {personna_bio}.
    Below is a poetic form from that world. Write a single poem that follows its rules exactly.
    Use the poem title if you can.

    RULES:
    - Follow the structure, meter, and rules described.
    - Use metaphor, vivid imagery, and emotional tone.
    - If the form is ribald, sacred, or sensual, match its spirit.
    - ONLY output the poem — no title, no author, no explanations, no annotations.
    - Do NOT include any metrical markings like (U/E), (EE), EV 1, or (E/E-E-E).
    - Do NOT add editorial notes, line numbers, or performance directions.
    - The output should be clean, flowing stanzas — as if recited aloud.
    - Do NOT include any XML or HTML tags, just plain text.
    - Do NOT use any modern slang or references, keep it timeless.


    POETIC FORM DESCRIPTION:
    {form_description}

    TITLE: "{title}"
    AUTHOR: {author}

    Think step by step but only output the final poem
    Now write the poem:
    """

    try:
        response = ollama.generate(
            model=MODEL,
            prompt=prompt,
            options={'num_predict': 300, 'temperature': 0.7}
        )
        return response['response'].strip()
    except Exception as e:
        return f"[Poem generation failed: {e}]"

def build_poet_personas(filepath: str, author_hfid_set: set) -> dict:
    """
    Build poetic personas ONLY for the given set of author HFIDs.
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Extract only <historical_figure> blocks that match our authors
    hf_blocks = re.findall(r'<historical_figure>(.*?)</historical_figure>', text, re.DOTALL)
    personas = {}

    for block in hf_blocks:
        hfid_match = re.search(r'<id>(\d+)</id>', block)
        if not hfid_match:
            continue
        hfid = int(hfid_match.group(1))
        if hfid not in author_hfid_set:
            continue  # Skip if not a poet in our list

        # Now parse this poet
        name_match = re.search(r'<name>(.*?)</name>', block)
        race_match = re.search(r'<race>(.*?)</race>', block)
        caste_match = re.search(r'<caste>(.*?)</caste>', block)
        birth_match = re.search(r'<birth_year>(-?\d+)</birth_year>', block)
        death_match = re.search(r'<death_year>(-?\d+)</death_year>', block)

        if not name_match:
            continue

        name = name_match.group(1).strip()
        race = race_match.group(1).strip().title() if race_match else "Unknown"
        caste = caste_match.group(1).strip().lower() if caste_match else "unknown"
        birth_year = int(birth_match.group(1)) if birth_match else None
        death_year = int(death_match.group(1)) if death_match else None
        lifespan = (death_year - birth_year) if birth_year and death_year else None

        # --- RELATIONSHIPS ---
        child_count = len(re.findall(r'<link_type>child</link_type>', block))
        deity_link = bool(re.search(r'<link_type>deity</link_type>', block))
        deity_strength_match = re.search(
            r'<hf_link>.*?<link_type>deity</link_type>.*?<link_strength>(\d+)</link_strength>.*?</hf_link>',
            block, re.DOTALL
        )
        deity_strength = int(deity_strength_match.group(1)) if deity_strength_match else 0

        # --- SKILLS ---
        skill_matches = re.findall(
            r'<hf_skill>.*?<skill>(.*?)</skill>.*?<total_ip>(\d+)</total_ip>.*?</hf_skill>',
            block, re.DOTALL
        )
        skills = {skill.lower(): int(ip) for skill, ip in skill_matches}

        # Score relevance
        poetic_skills = ['poetry', 'writing', 'speaking', 'storytelling']
        poetry_score = sum(skills.get(s.lower(), 0) for s in poetic_skills)

        # Top 3 relevant skills (above threshold)
        top_skills = [s for s, ip in sorted(skills.items(), key=lambda x: x[1], reverse=True) if ip > 500][:3]

        # --- BUILD PERSONA ---
        parts = [name]

        if poetry_score > 500:
            parts.append(f"a {race} poet")
        else:
            parts.append(f"a {race}")

        if lifespan:
            parts.append(f"who lived {lifespan} years")
        if child_count > 0:
            child_desc = "mother" if caste == "female" else "father" if caste == "male" else "parent"
            parts.append(f"{child_desc} of {child_count} children")
        if deity_link:
            strength = "deeply" if deity_strength > 80 else "tenuously"
            parts.append(f"{strength} bound to a deity")
        # if 'herbalism' in skills and skills['herbalism'] > 5000:
        #     parts.append("herbalist who weaves words into cures")
        # if 'lying' in skills and 'persuasion' in skills:
        #     parts.append("master of truth and deception")

        bio_summary = ", ".join(parts[1:])
        prompt_persona = f"{name}, {', '.join([p.lower() for p in parts[1:]])}"

        personas[hfid] = {
            'name': name,
            'bio_summary': bio_summary,
            'persona': prompt_persona,
            'poetry_score': poetry_score,
            'skills': skills,
            'lifespan': lifespan,
            'child_count': child_count,
            'deity_link': deity_link,
            'deity_strength': deity_strength
        }

    return personas



# --- MAIN ---
def main():
    print("🌑 Scanning legends.xml for poetic artifacts...")

    if not os.path.exists(LEGENDS_FILE):
        print(f"❌ {LEGENDS_FILE} not found!")
        return

    forms, works = parse_poetic_forms_and_works(LEGENDS_FILE)
    hf_names = load_hf_names(LEGENDS_FILE)
    
    # Step 2: Get ONLY authors of poems
    poem_authors = {work['author_hfid'] for work in works}  # set of unique HFIDs

    # Step 3: Build personas ONLY for these poets
    print(f"🧙‍♂️ Building personas for {len(poem_authors)} poets...")
    poet_personas = build_poet_personas(LEGENDS_FILE, poem_authors)

    worldname = "The Mountainous Prairie"  # You can customize this and it should come from the legends file
    
    OUTPUT_FILE = f'Codex of {worldname}.txt'
    print(f"✅ Found {len(forms)} poetic forms")
    print(f"✅ Found {len(works)} written works")
    print(f"📝 Compiling anthology: {OUTPUT_FILE}")


    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("════════════════════════════════════════════════════════════════════\n")
        f.write(f"     THE CODEX OF {worldname}\n")
        f.write( "     Lost Poems of a Procedurally Generated World\n")
        f.write("════════════════════════════════════════════════════════════════════\n\n")
        # After writing the header, add ToC
        f.write( " TABLE OF CONTENTS\n")
        f.write("════════════════════════════════════════════════════════════════════\n\n")

        # Sort works by title or author?
        toc_entries = []
        for work in works:
            if work['form_id'] in forms:
                author = hf_names.get(work['author_hfid'], "An Unknown Poet")
                toc_entries.append(f"{work['title']} .......................... {author}")

        # Sort alphabetically
        # toc_entries.sort()

        for entry in toc_entries:
            f.write(f"  {entry[:60]}\n")  # truncate if too long

        f.write("\n" + "─" * 80 + "\n\n")


        for i, work in enumerate(works):
            form_id = work['form_id']
            if form_id not in forms:
                continue  # Skip if form not found

            title = work['title']
            
            author_hfid = work['author_hfid']
            author_name = poet_personas.get(author_hfid, {}).get('name', "An Unknown Poet")
            author_bio = poet_personas.get(author_hfid)
            
            
            # author_name = hf_names.get(work['author_hfid'], "An Unknown Poet")
            form_desc = forms[form_id]
            # personna_bio = get_personna(author_name)
            
            # print(author_bio["bio_summary"])

            print(f"📜 Translating {i+1} of {len(works)}: '{title}' (Form ID {form_id})...")
            
            poem = generate_poem(form_desc, title=title, author=author_name, personna_bio=author_bio['persona'])

            
            f.write(f"✦ WORK: {title}\n")
            f.write(f"  Author: {author_name}\n")
            if author_bio:
                f.write(f"  Bio: {author_bio['bio_summary']}\n")
            f.write(f"  Form ID: {form_id}\n")
            f.write(f"  Type: {work['form_type']}\n\n")
            f.write(f"  {poem}\n")
            f.write("\n" + "─" * 80 + "\n\n")

    print(f" Anthology complete: {OUTPUT_FILE}")
    print(" The muse awakens.")


if __name__ == "__main__":
    main()