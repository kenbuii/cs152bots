import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report
import heapq
from openai import OpenAI
import pdb

# Set up logging to the console
logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = "tokens.json"
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    tokens = json.load(f)
    discord_token = tokens["discord"]
    # openai.api_key = tokens["openai"]

class ModBot(discord.Client):
    def __init__(self, openai_model='gpt-4o'):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=".", intents=intents)
        self.group_num = None

        self.user_channels = {}  # Map from guild to the user channel id for that guild
        self.mod_channels = {}  # Map from guild to the mod channel id for that guild

        self.reports = {}  # Map from user IDs to the state of their report
        self.pending_review = []  # Priority queue for reports that are pending review
        self.reviewed = []  # List of reports that have been reviewed
        self.report_ban = []  # List of users who cannot report

        self.openai_client = None
        self.openai_model = openai_model

    async def on_ready(self):
        print(f"{self.user.name} has connected to Discord! It is these guilds:")
        for guild in self.guilds:
            print(f" - {guild.name}")
        print("Press Ctrl-C to quit.")

        # Parse the group number out of the bot's name
        match = re.search("[gG]roup (\d+) [bB]ot", self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception(
                'Group number not found in bot\'s name. Name format should be "Group # Bot".'
            )
        
        self.openai_client = OpenAI()

        # Find the mod and user channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f"group-{self.group_num}-mod":
                    self.mod_channels[guild.id] = channel
                elif channel.name == f"group-{self.group_num}":
                    self.user_channels[guild.id] = channel

    async def on_message(self, message):
        """
        This function is called whenever a message is sent in a channel that the bot can see (including DMs).
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel.
        """
        # Ignore messages from the bot
        if message.author.id == self.user.id:
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        author_id = message.author.id

        # Handle a help message
        if message.content == Report.HELP_KEYWORD and author_id not in self.reports:
            reply = "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        if author_id in self.report_ban:
            await message.channel.send("You have been banned from reporting.")
            return

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(
            Report.START_KEYWORD
        ):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self, author_id)

        # Let the report class handle this message; forward all the messages it returns to us
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if author_id in self.reports and self.reports[author_id].report_complete():
            completed_report = self.reports.pop(author_id)
            heapq.heappush(self.pending_review, completed_report)

    async def handle_channel_message(self, message):
        user_channel = self.user_channels[message.guild.id]
        mod_channel = self.mod_channels[message.guild.id]

        if message.channel == mod_channel:
            await self.handle_mod_channel_message(message)
        elif message.channel == user_channel:
            await self.handle_user_channel_message(message)

    async def handle_user_channel_message(self, message):
        user_channel = self.user_channels[message.guild.id]
        await user_channel.send(
            f'Hello {message.author.name}! I heard you say "{message.content}" in the user channel.'
        )

        message_history = [
            m async for m in message.channel.history(around=message, limit=15)
        ]
        message_history = sorted(message_history, key=lambda m: m.created_at)

        evaluation = await self.eval_text(message, message_history)

        potential_victim_id = None
        for m in reversed(message_history):
            if m.author.id != message.author.id:
                potential_victim_id = m.author.id
                break

        if evaluation.get("sextortion", False):
            report = await Report.load_with_openai_client(self, potential_victim_id, message, message_history)
            heapq.heappush(self.pending_review, report)

    async def handle_mod_channel_message(self, message):
        mod_channel = self.mod_channels[message.guild.id]
        if message.content == Report.HELP_KEYWORD:
            reply = "Use the `review` command to begin the review process.\n"
            await message.channel.send(reply)
            return

        if message.content.startswith(Report.REVIEW_KEYWORD):
            if len(self.pending_review) == 0:
                await message.channel.send("No reports to review.")
                return
        
        report = self.pending_review[0]
        responses = await report.handle_review(message)
        for r in responses:
            await message.channel.send(r)

        if report.review_complete():
            self.reviewed.append(heapq.heappop(self.pending_review))

    async def eval_text(self, message, message_history):
        # Format the history for context
        formatted_history = "\n".join(
            [f"{m.author.name}: {m.content}" for m in message_history]
        )

        last_message_content = message_history[-1].content

        response = self.openai_client.chat.completions.create(
            model=self.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI assistant that helps evaluate messages for signs of sextortion. The user will provide a conversation history for context and a specific message to evaluate. Respond with a JSON object containing a boolean field 'sextortion'."
                },
                {
                    "role": "user",
                    "content": f"Conversation history:\n{formatted_history}\n\nEvaluate the following specific message for clear signs of sextortion:\n{last_message_content}\n\nRespond with a JSON object in the format: {{\"sextortion\": <true_or_false>}}"
                }
            ]
        )

        print(formatted_history)
        print(response.choices[0].message.content)

        try:
            evaluation = json.loads(response.choices[0].message.content.strip())
        except json.JSONDecodeError:
            evaluation = {"sextortion": False}

        return evaluation

    def code_format(self, text):
        """
        TODO: Once you know how you want to show that a message has been
        evaluated, insert your code here for formatting the string to be
        shown in the mod channel.
        """
        return "Evaluated: '" + text + "'"


client = ModBot()
client.run(discord_token)
