# CS 152 - Trust and Safety Engineering
## Discord Bot Framework Code

![cs152 final poster](https://github.com/kenbuii/cs152bots/assets/130824642/5c109a2c-2d57-48c8-b159-b752a0cff001)


## Guide To The Starter Code

Let’s take a look at what `bot.py` already does. To do this, run `bot.py` and leave it running in your terminal. Next, go into your team’s private group-# channel and try typing any message. You should see something like this pop up in the `group-#-mod` channel:


![Screenshot 2024-04-20 at 3 50 02 PM](https://github.com/stanfordio/cs152bots/assets/35933488/b5654bc6-8db1-4ea2-9f4c-5f4dca344058)


The default behavior of the bot is, that any time it sees a message (from a user), it sends that message to the moderator channel with no possible actions. This is not the final behavior you’ll want for your bot - you should update this to match your report flow. However, the infrastructure is there for your bot to automatically flag messages and (potentially) moderate them somehow.

Next up, click on your app in the right sidebar under “Online” to begin direct messaging it (or click on its name). First of all, try sending “help”. You should see a response like this (but with your group number instead of Group 0):


![Screenshot 2024-04-20 at 3 50 29 PM](https://github.com/stanfordio/cs152bots/assets/35933488/6ff900e9-03c0-44b0-be0b-5b4515abcbcb)



Try following its instructions from there by reporting a message from one of the channels to get a sense for the reporting flow that’s already built out for you. (Make sure to only report messages from channels that the bot is also in.)


## Troubleshooting

### `Exception: tokens.json not found`!

If you’re seeing this error, it probably means that your terminal is not open in the right folder. Make sure that it is open inside the folder that contains bot.py and tokens.json. You can check this by typing in ls and verifying that the output looks something like this:

```
	# ls
	bot.py 	tokens.json
```

 ### `SSL: CERTIFICATE_VERIFY_FAILED error`

Discord has a slight incompatibility with Python3 on Mac. To solve this, navigate to your /Applications/Python 3.6/ folder and double click the Install Certificates.command. Try running the bot again; it should be able to connect now. 

If you’re still having trouble, try running a different version of Python (i.e. use the command python3.7 or python3.8) instead. If that doesn’t work, come to section and we’ll be happy to help!


### `intents has no attribute message_content error`

This is an issue with the version of Discord API that is installed. Try the following steps: 
1. running ```pip install --upgrade``` discord in the terminal in your folder in the project that contains this file
2. IF that does not work, try changing the line in bot.py that says ```intents.message_content = True``` to  ```intents.messages = True```


## Resources

Below are some resources we think might be useful to you for this part of the milestone. 

[Here](https://discordpy.readthedocs.io/en/latest/) is the documentation for `discord.py`, Discord’s Python package for writing Discord bots. It’s very thorough and fairly readable; this plus Google (in addition to the TAs) should be able to answer all of your functionality questions!

Discord bots frequently use emoji reactions as a quick way to offer users a few choices - this is especially convenient in a setting like moderation when mods may have to make potentially many consecutive choices. Check out [`on_raw_reaction_add()`](https://discordpy.readthedocs.io/en/latest/api.html?highlight=on_reaction_add#discord.on_raw_reaction_add) for documentation about how to do this with your bot. You also might want to look into [`on_raw_message_edit()`](https://discordpy.readthedocs.io/en/latest/api.html?highlight=edit#discord.on_raw_message_edit) to notice users editing old messages.

Discord offers “embeds” as a way of getting a little more control over message formatting. Read more about them in [this](https://python.plainenglish.io/send-an-embed-with-a-discord-bot-in-python-61d34c711046) article or in the [official documentation](https://discordpy.readthedocs.io/en/latest/api.html?highlight=embeds#discord.Embed).

[`unicode`](https://pypi.org/project/Unidecode/) and [`uni2ascii-janin`](https://pypi.org/project/uni2ascii-janin/) are two packages that can help with translating `unicode` characters to their `ascii` equivalents.
