#!/usr/bin/env bash
# Ingest a batch of classic public-domain books from Project Gutenberg.
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python

# format: id|owner|caption
BOOKS=(
  "1342|alice|Pride and Prejudice — Jane Austen."
  "84|bob|Frankenstein — Mary Shelley."
  "1661|alice|The Adventures of Sherlock Holmes — Arthur Conan Doyle."
  "174|bob|The Picture of Dorian Gray — Oscar Wilde."
  "345|alice|Dracula — Bram Stoker."
  "98|bob|A Tale of Two Cities — Charles Dickens."
  "35|alice|The Time Machine — H. G. Wells."
  "120|bob|Treasure Island — Robert Louis Stevenson."
  "1400|alice|Great Expectations — Charles Dickens."
  "844|bob|The Importance of Being Earnest — Oscar Wilde."
  "1232|alice|The Prince — Niccolò Machiavelli."
  "203|bob|Uncle Tom's Cabin — Harriet Beecher Stowe."
  "16|alice|Peter Pan — J. M. Barrie."
  "76|bob|Adventures of Huckleberry Finn — Mark Twain."
  "74|alice|The Adventures of Tom Sawyer — Mark Twain."
)
for entry in "${BOOKS[@]}"; do
  IFS="|" read -r id owner caption <<<"$entry"
  echo "===== $caption ====="
  $PY ingest.py "https://www.gutenberg.org/ebooks/$id.epub.images" "$owner" "$caption" || echo "  (failed, continuing)"
done
echo "done."
