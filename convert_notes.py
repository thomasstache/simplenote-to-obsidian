#!/usr/bin/env python3

import json
import os
import re
import shutil
import sys
from datetime import datetime
from enum import Enum
from subprocess import call

# Path to the JSON file we'll read in:
INPUT_FILE = "./notes.json"
# INPUT_FILE = "./notes-short.json"
# INPUT_FILE = "./notes-dates.json"

# Path to the directory where we'll save the converted notes:
OUTPUT_DIRECTORY = "./notes_converted/"

# Should the creation time of the created files be set to the creation
# time of the original notes?
# Will fail if you're not on a Mac, or don't have Xcode installed -
# in which case set this to False.
KEEP_ORIGINAL_CREATION_TIME = True

# Should the last-modified time of the created files be set to the
# last-modified time of the original notes?
KEEP_ORIGINAL_MODIFIED_TIME = True


class TagPosition(Enum):
    YAML = 1
    START = 2
    END = 3


def check_dates_in_title(properties: list[str], note_title):
    """
    Check for date patterns in the note title and add a 'date' field to note properties if found.

    :param properties: list of properties
    :param note_title: str
    """

    # first element is the regex pattern, second is the date format to parse the matched string
    date_patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', "%Y-%m-%d"),  # YYYY-M-D or YYYY-MM-DD
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', "%Y/%m/%d"),  # YYYY/M/D or YYYY/MM/DD
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', "%m/%d/%Y"),  # M/D/YYYY or MM/DD/YYYY
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', "%d-%m-%Y"),  # D-M-YYYY or DD-MM-YYYY
        (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', "%d.%m.%Y"),  # D.M.YYYY or DD.MM.YYYY
        (r'(\d{1,2})\.(\d{1,2})\.(\d{2})', "%d.%m.%y"),  # D.M.YY or DD.MM.YY
    ]
    for pattern, date_format in date_patterns:
        match = re.search(pattern, note_title)
        if match:
            date_str = match.group(0)
            try:
                date_obj = datetime.strptime(date_str, date_format)
                properties.append(f"date: {date_obj.strftime('%Y-%m-%d')}")
            except ValueError:
                pass
            break


def main():
    ###################################################################
    # 1. Set-up and checking.

    if not os.path.exists(INPUT_FILE):
        sys.exit(f"There is no file at {INPUT_FILE}")

    if not os.path.isfile(INPUT_FILE):
        sys.exit(f"{INPUT_FILE} is not a file")

    tag_position: TagPosition = TagPosition.END
    tag_position_input = input("\nWhere should tags be put? Either YAML (1), start (2) or end (3) (default is '3'): ")

    if tag_position_input == "":
        tag_position = TagPosition.END
    elif tag_position_input == "1":
        tag_position = TagPosition.YAML
    elif tag_position_input == "2":
        tag_position = TagPosition.START
    elif tag_position_input == "3":
        tag_position = TagPosition.END
    else:
        sys.exit("Select either 'yaml', 'start' or 'end'. Please rerun the script.")

    if os.path.exists(OUTPUT_DIRECTORY):
        # rename existing output directory
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_name = f"{OUTPUT_DIRECTORY.rstrip('/')}_backup_{timestamp}/"
        print(f"\nRenaming existing output directory to {new_name}\n")
        shutil.move(OUTPUT_DIRECTORY, new_name)

    if not os.path.isdir(OUTPUT_DIRECTORY):
        os.mkdir(OUTPUT_DIRECTORY)

    ###################################################################
    # 2. Loop through all the notes and create new ones

    # Empty line before next output
    print("")

    # The keys will be filenames, the values will be an integer -
    # the number of times that filename was used.
    filenames = {}

    with open(INPUT_FILE, encoding="UTF-8") as json_file:
        # Load the JSON data into a dict:
        try:
            data = json.load(json_file)
        except json.decoder.JSONDecodeError as e:
            sys.exit(f"Could not parse {INPUT_FILE}. Are you sure it's a JSON file?")

        if not isinstance(data, dict):
            sys.exit(f"The data from {INPUT_FILE} is not a dict, so it can't be used.")

        if "activeNotes" not in data:
            sys.exit(f"There is no 'activeNotes' element in the data found in {INPUT_FILE}")

        for note in data["activeNotes"]:
            # Get all the note's lines into a list:
            lines = note["content"].splitlines()
            meta_data = {
                "is_markdown": (note.get("markdown") or False) is True,
                "creationDate": datetime.strptime(note["creationDate"], "%Y-%m-%dT%H:%M:%S.%fZ"),
                "lastModified": datetime.strptime(note["lastModified"], "%Y-%m-%dT%H:%M:%S.%fZ"),
            }
            frontmatter = []

            if len(lines) == 0:
                # We'll skip any empty notes
                print(f"Skipping empty note with ID of {note['id']}")
            else:
                # Create the new filename/path based on the first line of the note:
                # But trim it to 248 characters so we can keep the entire thing -
                # with the possible extra digit(s) added below - under 255 characters.
                note_title = lines[0].strip()

                # many note titles may start with a '#' for a Markdown title, so remove that first:
                if meta_data["is_markdown"] or note_title.startswith('#'):
                    note_title = note_title.lstrip('#').strip()
                    # remove the title line
                    lines = lines[1:]
                    while lines[0].strip() == "":
                        lines = lines[1:]

                if len(note_title) > 248:
                    filename = note_title[0:248] + ".md"
                else:
                    filename = note_title + ".md"

                # Need to remove any forward slashes or colons:
                filename = filename.replace("/", "").replace(":", "")
                filepath = os.path.join(OUTPUT_DIRECTORY, filename)

                # Keep track of this filename and how many times it's been used:
                if filename in filenames:
                    filenames[filename] += 1
                else:
                    filenames[filename] = 1

                if os.path.exists(filepath):
                    # Don't want to overwrite it!
                    # So, remove .md, and add the count of how many times this filename
                    # has been used to the end, to make it unique.
                    filename = f"{filename[:-3]} {filenames[filename]}.md"
                    filepath = os.path.join(OUTPUT_DIRECTORY, filename)

                # print(f"Writing {note['id']} to '{filepath}'")

                if "tags" in note:
                    tags = note["tags"]

                    # Replace any non-word characters in each tag with a hyphen:
                    tags = [re.sub(r'\W+', '-', tag) for tag in tags]

                    if tag_position == TagPosition.YAML:
                        add_tags_to_front_matter(frontmatter, tags)
                    else:
                        add_legacy_tags(lines, tags, tag_position)

                # check title for date patterns
                check_dates_in_title(frontmatter, note_title)

                if "creationDate" in meta_data:
                    frontmatter.append(f"simplenote-created: {meta_data['creationDate'].strftime('%Y-%m-%dT%H:%M:%SZ')}")

                if len(frontmatter) > 0:
                    prepend_front_matter(lines, frontmatter)

                with open(filepath, "w", encoding="UTF-8") as outfile:
                    outfile.write("\n".join(lines))

                if KEEP_ORIGINAL_CREATION_TIME:
                    creation_time = meta_data["creationDate"].strftime("%m/%d/%Y %H:%M:%S %p")
                    call(["SetFile", "-d", creation_time, filepath])

                if KEEP_ORIGINAL_MODIFIED_TIME:
                    # Set the file access and modified times:
                    modified_time = meta_data["lastModified"].timestamp()
                    os.utime(filepath, (modified_time, modified_time))

    num_files = sum(filenames.values())
    files_were = "file was" if num_files == 1 else "files were"
    print(f"\n{num_files} .md {files_were} created in {OUTPUT_DIRECTORY}")


# Create the YAML front-matter block
def prepend_front_matter(lines: list[str], properties: list[str]):
    frontmatter = ["---", *properties, "---"]
    lines[0:0] = frontmatter


# Write tags into Front-Matter
def add_tags_to_front_matter(frontmatter: list[str], tags: list[str]):
    frontmatter.append("tags:")
    for tag in tags:
        frontmatter.append(f"  - {tag}")


def add_legacy_tags(lines, tags: list[str], tag_position: TagPosition):
    # Prefix tags with # so obsidian recognises them as tags:
    tags = ["#" + tag for tag in tags]

    # Create the tag text we'll insert into the new note:
    tag_text = " ".join(tags)

    if tag_position == TagPosition.START:
        lines.insert(1, "")
        lines.insert(2, tag_text)
    else:
        lines.append("")
        lines.append(tag_text)


if __name__ == "__main__":
    main()
