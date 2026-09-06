"""CSS/XPath selectors for Google Flow UI.

Centralized here so they can be updated easily when Google changes the UI.
All selectors target the labs.google/fx/tools/flow interface.
"""

# =============================================================================
# Flow Home / Landing
# =============================================================================

FLOW_BASE_URL = "https://labs.google/fx/tools/flow"
FLOW_EDITOR_URL = "https://labs.google/fx/tools/flow/create"

# Google account avatar — presence indicates logged in
AVATAR_SELECTOR = 'img[alt*="Google Account"], button[aria-label*="Google Account"]'

# Sign-in button on Flow landing page
SIGN_IN_BTN = 'a[href*="accounts.google.com"], button:has-text("Sign in")'

# Landing page CTA buttons to enter the app
CREATE_WITH_FLOW_BTN = 'button:has-text("Create with Google Flow"), button:has-text("Try in Google Flow")'

# =============================================================================
# Flow Create / Editor Page
# =============================================================================

# Main prompt input area
PROMPT_INPUT = 'textarea:visible, div[contenteditable="true"]:visible, textarea, [contenteditable="true"]'

# Generate / Create button
GENERATE_BTN = 'button:has-text("Generate"), button:has-text("Create"), button[aria-label*="Generate"]'

# =============================================================================
# Tool / Mode Selection (Video, Image, Music)
# =============================================================================

# Tool selector tabs or buttons
VIDEO_TOOL_BTN = 'button:has-text("Video"), a:has-text("Video"), [data-tool="video"]'
IMAGE_TOOL_BTN = 'button:has-text("Image"), a:has-text("Image"), [data-tool="image"]'
MUSIC_TOOL_BTN = 'button:has-text("Music"), a:has-text("Music"), [data-tool="music"]'

# Style/preset selectors
STYLE_SELECTOR = 'button[aria-label*="style"], [data-style]'

# Aspect ratio controls
ASPECT_RATIO_BTN = 'button[aria-label*="aspect"], button:has-text("16:9"), button:has-text("9:16")'

# Duration controls
DURATION_INPUT = 'input[type="range"][aria-label*="uration"], input[type="number"][aria-label*="uration"]'

# =============================================================================
# Results / Output Area
# =============================================================================

# Generated video element
VIDEO_RESULT = 'video[src], video, [data-video], [class*="video-result"], [class*="output"] video, [class*="creation"] video, button[aria-label*="ownload"]'

# Generated image element
IMAGE_RESULT = 'img[src*="generated"], img[src*="output"], img[data-generated], [class*="output"] img, [class*="creation"] img'

# Audio/music result
AUDIO_RESULT = 'audio[src], audio source[src], audio, [data-audio]'

# Download button for the result
DOWNLOAD_BTN = 'button[aria-label*="ownload"], button:has-text("Download"), a[download], [data-icon="download"]'

# Share / link button
SHARE_BTN = 'button[aria-label*="hare"], button:has-text("Share")'

# =============================================================================
# Loading / Progress Indicators
# =============================================================================

# Spinner or progress bar during generation
LOADING_INDICATOR = '[role="progressbar"], [class*="spinner"], [class*="loading"], [aria-busy="true"]'

# "Generating..." text
GENERATING_TEXT = ':text("Generating"), :text("Creating"), :text("Processing")'

# Error messages
ERROR_INDICATOR = '[class*="error"], [role="alert"], :text("Something went wrong")'

# =============================================================================
# Gallery / History
# =============================================================================

# Gallery item cards
GALLERY_ITEM = '[class*="gallery"] [class*="item"], [class*="creation"], [data-creation-id]'

# Gallery item thumbnail
GALLERY_THUMBNAIL = '[class*="gallery"] img, [class*="creation"] img'

# =============================================================================
# Navigation
# =============================================================================

# "New creation" or "Create new" button
NEW_CREATION_BTN = 'button:has-text("New"), button:has-text("Create new"), a:has-text("New")'

# Back to gallery
BACK_BTN = 'button[aria-label*="Back"], a[aria-label*="Back"]'
