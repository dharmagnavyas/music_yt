import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import logging
import openai
from langchain_core.tools import tool
from langchain_community.tools import YouTubeSearchTool
from langchain.prompts import PromptTemplate
from langchain_openai.chat_models import ChatOpenAI
from langchain.agents import create_react_agent

# Configure logging
logging.basicConfig(level=logging.INFO)

# Spotify API credentials
SPOTIPY_CLIENT_ID = 'e3aad9971893477c9e432852a44900b3'
SPOTIPY_CLIENT_SECRET = '5c24037218dd459cae5dad33f74880f9'
SPOTIPY_REDIRECT_URI = 'http://localhost:61590/callback/'  # Ensure this port matches below

scope = 'user-library-read user-top-read playlist-modify-private playlist-modify-public'

auth_manager = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                            client_secret=SPOTIPY_CLIENT_SECRET,
                            redirect_uri=SPOTIPY_REDIRECT_URI,
                            scope=scope)

# Get the authorization URL
auth_url = auth_manager.get_authorize_url()
logging.info("Please go to this URL and authorize the application: %s", auth_url)

# Shared variable to store the authorization code
auth_code = None

# Run a simple HTTP server to handle the callback
class SpotifyAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        if self.path.startswith('/callback'):
            query_components = parse_qs(urlparse(self.path).query)
            auth_code = query_components.get('code', [None])[0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Authorization successful. You can close this window.')
            logging.info("Authorization code received: %s", auth_code)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

def run_server():
    server_address = ('localhost', 61590)  # Ensure this port matches above
    httpd = HTTPServer(server_address, SpotifyAuthHandler)
    logging.info('Server started at http://localhost:61590/callback/')
    httpd.handle_request()

# Run the server in a separate thread
server_thread = threading.Thread(target=run_server)
server_thread.start()

# Wait for the server to get the auth code
server_thread.join()

# Ensure the auth_code is retrieved
if not auth_code:
    raise Exception("Failed to get authorization code")

# Exchange the authorization code for an access token
token_info = auth_manager.get_access_token(auth_code, as_dict=False)

# Use the access token to interact with the Spotify API
sp = spotipy.Spotify(auth_manager=auth_manager)

@tool("spotify_top_tracks")
def get_spotify_top_tracks() -> str:
    """Get the top tracks from the user's Spotify account."""
    results = sp.current_user_top_tracks(limit=10)
    top_tracks = [track['name'] for track in results['items']]
    return f"Here are your top tracks: {', '.join(top_tracks)}"

# Set your OpenAI API key
openai.api_key = 'sk-proj-YMLNcXKNxILzLKqET0zzT3BlbkFJt2iZ1JqfjT358uXMVsZ4'

# Define the language model using langchain_openai
llm = ChatOpenAI(api_key=openai.api_key, model="gpt-3.5-turbo")  # Correct initialization

# Load tools including human input and YouTube search
youtube_search_tool = YouTubeSearchTool()
tools = [youtube_search_tool, get_spotify_top_tracks]

tool_names = [tool.name for tool in tools]

# Create a PromptTemplate
initial_prompt = """
You are a helpful assistant that provides suggestions based on user input.
Available tools: {tool_names}
Use the following tools to assist you:
{tools}
Agent scratchpad: {agent_scratchpad}
User input: {input}

You must respond with a JSON object containing the following keys:
- "thoughts": a string describing your thought process
- "action": the name of the tool to use
- "action_input": the input parameters for the tool

For example:
```json
{
  "thoughts": "I will use the SpotifyTopTracks tool to get the user's top tracks.",
  "action": "SpotifyTopTracks",
  "action_input": {}
}
```
"""

prompt_template = PromptTemplate(
    input_variables=["input", "tool_names", "tools", "agent_scratchpad"],
    template=initial_prompt
)

# Initialize the agent using the new method
agent_chain = create_react_agent(
    tools=tools,
    llm=llm,
    prompt=prompt_template
)

# Custom function to handle the agent execution
def execute_custom_agent(input_text):
    # Create the input for the agent executor
    input_dict = {
        "input": input_text,
        "tool_names": tool_names,
        "tools": tools,
        "agent_scratchpad": "",
        "intermediate_steps": []  # Ensure intermediate_steps is included
    }
    # Execute the agent using invoke
    response = agent_chain.invoke(input_dict)
    return response

# Example usage
input_text = "Can you tell me my top tracks?"
response = execute_custom_agent(input_text)
logging.info(response)

input_text = "Search for Mr.Beast videos on YouTube"
response = execute_custom_agent(input_text)
logging.info(response)
