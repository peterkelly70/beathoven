#!/bin/bash

# Load MANS_DIR from the .env file
set -a # automatically export all variables
source .env
set +a

# Check if MANS_DIR is set
if [ -z "$MAN_DIR" ]; then
    echo "MAN_DIR is not set in the .env file."
    exit 1
fi

# Subdirectories and example files
declare -A sections=(
  ["Getting_Started/01_Inviting_Beathoven.md"]="How to invite Beathoven to your Discord server."
  ["Getting_Started/02_Permissions_Required.md"]="List of permissions required by Beathoven."
  ["Commands/Basic_Commands/01_Join_Leave.md"]="How to use the !join and !leave commands."
  ["Commands#!/bin/bash

# Load MANS_DIR from the .env file
set -a # automatically export all variables
source /path/to/your/.env
set +a

# Check if MANS_DIR is set
if [ -z "$MANS_DIR" ]; then
    echo "MANS_DIR is not set in the .env file."
    exit 1
fi

# Subdirectories and example files
declare -A sections=(
  ["Getting_Started/01_Inviting_Beathoven.md"]="How to invite Beathoven to your Discord server."
  ["Getting_Started/02_Permissions_Required.md"]="List of permissions required by Beathoven."
  ["Commands/Basic_Commands/01_Join_Leave.md"]="How to use the !join and !leave commands."
  ["Commands/Basic_Commands/02_Play_Add_Remove.md"]="Guide on using !play, !add, and !remove commands."
  ["Commands/Playback_Control/01_Pause_Resume_Skip.md"]="Instructions for !pause, !resume, and !skip."
  ["Commands/Playback_Control/02_Volume_Adjustment.md"]="How to adjust playback volume with !volume."
  ["Commands/Playlist_Management/01_Creating_Saving_Playlists.md"]="Creating and saving playlists."
  ["Advanced_Features/01_Repeat_Modes.md"]="Explanation of repeat modes."
)

# Iterate over sections and create directories/files
for path in "${!sections[@]}"; do
  full_path="$MAN_DIR/$path"
  mkdir -p "$(dirname "$full_path")" # Create the directory structure
  echo "${sections[$path]}" > "$full_path" # Create the file with example content
done

echo "Documentation structure created successfully."
s/Playback_Control/01_Pause_Resume_Skip.md"]="Instructions for !pause, !resume, and !skip."
  ["Commands/Playback_Control/02_Volume_Adjustment.md"]="How to adjust playback volume with !volume."
  ["Commands/Playlist_Management/01_Creating_Saving_Playlists.md"]="Creating and saving playlists."
  ["Advanced_Features/01_Repeat_Modes.md"]="Explanation of repeat modes."
)

# Iterate over sections and create directories/files
for path in "${!sections[@]}"; do
  full_path="$MAN_DIR/$path"
  mkdir -p "$(dirname "$full_path")" # Create the directory structure
  echo "${sections[$path]}" > "$full_path" # Create the file with example content
done

echo "Documentation structure created successfully."
