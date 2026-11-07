# ghnewmodels

`ghnewmodels` checks a GitHub Enterprise Copilot models page for models whose policy is set to **Delegate to default policy**. It prints the matching model names and can send the results to Slack and/or Discord via webhooks.

The script runs a check when it starts, then checks again every hour at 15 minutes past the hour.

## Requirements

- Python 3.12 or later
- Access to the GitHub Enterprise Copilot models page
- Chromium, installed through Playwright

## Setup

Clone the repository and enter its directory:

```bash
git clone https://github.com/yesnowman/ghnewmodels.git
cd ghnewmodels
```

Install the Python dependencies and Playwright's Chromium browser:

```bash
python3 -m pip install requests playwright
python3 -m playwright install chromium
```

## Run

Pass your GitHub Enterprise slug as the first argument:

```bash
python3 ghnewmodels.py YOUR_ENTERPRISE_SLUG
```

The script opens a visible Chromium window. Sign in to GitHub in that window if prompted. The browser profile is stored at `~/.newmodels-playwright`, so the session may persist between runs.

## Optional notifications

You can provide Slack and Discord webhook URLs as the second and third arguments:

```bash
python3 ghnewmodels.py YOUR_ENTERPRISE_SLUG SLACK_WEBHOOK_URL DISCORD_WEBHOOK_URL
```

To use only one notification service, pass `OFF` for the other:

```bash
python3 ghnewmodels.py YOUR_ENTERPRISE_SLUG SLACK_WEBHOOK_URL OFF
python3 ghnewmodels.py YOUR_ENTERPRISE_SLUG OFF DISCORD_WEBHOOK_URL
```

Keep webhook URLs private. Stop the script with `Ctrl+C`.
