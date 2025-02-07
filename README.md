# testbot_tg
A Telegram bot built using NoneBot.

## Features
* **Echo Plugin:**  A built-in plugin that echoes back received messages.
* **Shutdown Plugin:** Allows for controlled shutdown of the bot.
* **Status Plugin:** Provides information about the bot's status.
* **Logpile Plugin:**  Manages and displays logs.
* **YetAnotherPicSearch Plugin:** Reverse image search capabilities (using SauceNAO and Ascii2D).
* **DeepSeek Plugin:**  Integration with DeepSeek API for various functionalities.
* **Example Plugins:** Demonstrates various functionalities:
    * Downloading files.
    * Inline query handling.
    * Mentioning users.
    * Sending photos (various methods).
    * Replying to messages.
    * Sending various message types (emoji, location, venue, poll, dice, chat actions).

## Usage
1. **Generate Project:** Use `nb create` to generate a new NoneBot project.
2. **Install Plugins:**  Install necessary plugins using `nb plugin install <plugin_name>`.  See `pyproject.toml` for the list of plugins.
3. **Run Bot:** Start the bot with `nb run`.

## Installation
1.  Ensure you have Python 3.9 or higher installed.
2.  Clone the repository: `git clone <repository_url>`
3.  Navigate to the project directory: `cd testbot_tg`
4.  Create a virtual environment (recommended): `python3 -m venv .venv`
5.  Activate the virtual environment: `. .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows)
6.  Install dependencies: `pip install -r requirements.txt` (if `requirements.txt` exists; otherwise install from `pyproject.toml`)
7.  Obtain API keys for SauceNAO, DeepSeek, and OpenAI (if needed), and add them to your environment variables or a `.env` file. Configure these in `driver.config` within `bot.py`.

## Technologies Used
* **NoneBot:** A powerful and versatile framework for building bots.
* **NoneBot Adapter Telegram:** An adapter allowing NoneBot to interact with the Telegram platform.
* **FastAPI:**  A modern, fast (high-performance), web framework for building APIs.  Used by NoneBot.
* **httpx:**  An HTTP client for Python, used for making requests.
* **Python:** The programming language used for the bot's logic.
* **Git:** Used for version control.
* **GitHub Actions:** Used for CI/CD (Continuous Integration/Continuous Deployment).  Specifically for logging commits and deploying documentation.
* **Node.js & npm:** Used for building the documentation website with VitePress.
* **VitePress:** Static site generator for the project documentation.
* **Awk:** Used in the GitHub Actions workflow for text processing.

## Configuration
Bot configuration is primarily handled within `bot.py`.  API keys for services like SauceNAO and DeepSeek should be configured here.  Refer to the `pyproject.toml` for plugin configurations.  The example plugins within the `plugins/example` directory also contain code that helps customize your bot's functionality.  Example configuration values are shown below, but replace placeholders with your actual tokens.

```python
driver.config.telegram_bots=[{'token': 'YOUR_TELEGRAM_BOT_TOKEN'}]
driver.config.saucenao_api_key='YOUR_SAUCENAO_API_KEY'
driver.config.deepseek={'api_key': 'YOUR_DEEPSEEK_API_KEY'}
driver.config.openai_api_key='YOUR_OPENAI_API_KEY'

```

## Dependencies
Refer to `pyproject.toml` for the list of project dependencies managed by `pip`.  Additional dependencies may be specified in `requirements.txt` (if present).

## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

## Testing
No formal testing framework is currently implemented, but the example plugins serve as functional demonstrations and integration tests.

## GitHub Actions Workflows
Two workflows are defined in the `.github/workflows` directory:

* **`commit_log.yml`**: This workflow logs commit details to `workflow.log` and updates `docpage/docs/workflow.md` on every push.
* **`deploy.yml`**: This workflow builds the documentation website using VitePress and deploys it to the `gh-pages` branch.  Requires Node.js and npm to be installed.

## API Documentation
API Documentation

This Telegram bot utilizes NoneBot's built-in FastAPI server for handling API requests.  Currently, no dedicated public API endpoints are exposed beyond the standard Telegram Bot API interaction.  All functionality is accessed through the Telegram bot itself.  Future versions may include additional, publicly accessible API endpoints.

Authentication:  Interaction requires a Telegram Bot token, which is configured within `bot.py`.  No other authentication mechanisms are implemented.

Example Interaction (Telegram Bot API):

Sending a message:

```json
{
  "method": "sendMessage",
  "chat_id": 123456789, // Replace with your chat ID
  "text": "Hello from the API!"
}
```

Receiving a message:  The bot receives messages through the Telegram Bot API webhook.  The structure of received messages depends on the message type.  See the Telegram Bot API documentation for details.

Example Plugins using Internal APIs:

Several plugins in this repository utilize internal APIs within the NoneBot framework, such as for image search, status retrieval and file download.  These are not publicly accessible endpoints but examples of how to integrate with the Telegram Bot API and utilize NoneBot's features.  Refer to the code within the `plugins` directory for examples.

*README.md was made with [Etchr](https://etchr.dev)*