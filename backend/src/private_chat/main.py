from private_chat.bootstrap import create_app
from private_chat.config import Settings

# Configuration is validated before accepting traffic. Missing encryption credentials
# therefore stop startup instead of silently falling back to plaintext storage.
app = create_app(Settings())
