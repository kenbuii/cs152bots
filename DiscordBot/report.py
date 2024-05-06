from enum import Enum, auto
from dataclasses import dataclass
import discord
import re


class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE_LINK = auto()
    AWAITING_REPORT_REASON = auto()
    AWAITING_REASON_SPECIFICS = auto()
    AWAITING_MINOR_INDICATION = auto()
    AWAITING_REPORT_CONFIRMATION = auto()
    AWAITING_BLOCK_DECISION = auto()
    REPORT_COMPLETE = auto()


class ReportReason(Enum):
    NUDITY_SEXUAL_CONTENT = "Nudity and Sexual Content"
    HARASSMENT_ABUSE = "Harassment and Abuse"
    GRAPHIC_CONTENT = "Graphic Content"
    OFFENSIVE_CONTENT = "Offensive Content"
    SPAM = "Spam"


class ReasonSubtype(Enum):
    CONTAINS_EXPLICIT_CONTENT = "Contains explicit content"
    SEEMS_LIKE_SEXUAL_EXPLOITATION = "Seems like sexual exploitation"
    THREAT_TO_SHARE_NUDE_IMAGES = "It's a threat to share my nude images"
    NUDE_IMAGES_SHARED = "My nude images have been shared"
    SEXUAL_HARASSMENT = "Sexual Harassment"
    TARGETED_HARASSMENT = "Targeted Harassment"
    HATE_SPEECH = "Hate Speech"


@dataclass
class ReasonSubtypeInfo:
    name: ReasonSubtype
    ask_if_user_is_minor: bool = False


@dataclass
class ReportReasonInfo:
    name: ReportReason
    question_text: str = None
    subtypes: list[ReasonSubtypeInfo] = None


class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    REPORT_REASON_INFOS = [
        ReportReasonInfo(
            name=ReportReason.NUDITY_SEXUAL_CONTENT,
            question_text="How does this contain Nudity or Sexual Content?",
            subtypes=[
                ReasonSubtypeInfo(name=ReasonSubtype.CONTAINS_EXPLICIT_CONTENT),
                ReasonSubtypeInfo(name=ReasonSubtype.SEEMS_LIKE_SEXUAL_EXPLOITATION),
                ReasonSubtypeInfo(
                    name=ReasonSubtype.THREAT_TO_SHARE_NUDE_IMAGES,
                    ask_if_user_is_minor=True,
                ),
                ReasonSubtypeInfo(
                    name=ReasonSubtype.NUDE_IMAGES_SHARED, ask_if_user_is_minor=True
                ),
            ],
        ),
        ReportReasonInfo(
            name=ReportReason.HARASSMENT_ABUSE,
            question_text="How is this Harassment or abuse?",
            subtypes=[
                ReasonSubtypeInfo(
                    name=ReasonSubtype.THREAT_TO_SHARE_NUDE_IMAGES,
                    ask_if_user_is_minor=True,
                ),
                ReasonSubtypeInfo(
                    name=ReasonSubtype.NUDE_IMAGES_SHARED, ask_if_user_is_minor=True
                ),
                ReasonSubtypeInfo(name=ReasonSubtype.SEXUAL_HARASSMENT),
                ReasonSubtypeInfo(name=ReasonSubtype.HATE_SPEECH),
                ReasonSubtypeInfo(name=ReasonSubtype.TARGETED_HARASSMENT),
            ],
        ),
        ReportReasonInfo(name=ReportReason.GRAPHIC_CONTENT),
        ReportReasonInfo(name=ReportReason.OFFENSIVE_CONTENT),
        ReportReasonInfo(name=ReportReason.SPAM),
    ]

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.report_reason = None
        self.reason_subtype = None
        self.user_is_minor = None

    async def handle_message(self, message):
        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]

        if message.content == self.HELP_KEYWORD:
            return [
                "To report a message:",
                "1. Use the `report` command",
                "2. Provide the message link when prompted",
                "3. Select a report reason from the menu",
                "4. Provide specifics and confirm the report",
                "\nYou can cancel at any time by saying `cancel`.",
            ]

        if self.state == State.REPORT_START:
            reply = "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE_LINK
            return [reply]

        if self.state == State.AWAITING_MESSAGE_LINK:
            m = re.search("/(\d+)/(\d+)/(\d+)", message.content)
            if not m:
                return [
                    "I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."
                ]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return [
                    "I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."
                ]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return [
                    "It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."
                ]
            try:
                self.message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return [
                    "It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."
                ]

            self.state = State.AWAITING_REPORT_REASON

            reply = "I found this message:"
            reply += "\n```"
            reply += self.message.author.name + ": " + self.message.content
            reply += "```\n"
            reply += "**What is the reason for this report?**\n"
            for i, reason in enumerate(self.REPORT_REASON_INFOS, 1):
                reply += f"`[{i}]` {reason.name.value}\n"
            reply += "\n*Please reply with a number from the options above.*"
            return [reply]

        if self.state == State.AWAITING_REPORT_REASON:
            try:
                index = int(message.content) - 1
                self.report_reason = self.REPORT_REASON_INFOS[index]
            except (ValueError, IndexError):
                return [
                    "Invalid input. Please enter the number corresponding to the report reason."
                ]

            if not self.report_reason.subtypes:
                return self.ask_for_confirmation()

            self.state = State.AWAITING_REASON_SPECIFICS

            reply = f"**{self.report_reason.question_text}**\n"
            for i, subtype in enumerate(self.report_reason.subtypes, 1):
                reply += f"`[{i}]` {subtype.name.value}\n"
            reply += "\n*Please reply with a number from the options above.*"
            return [reply]

        if self.state == State.AWAITING_REASON_SPECIFICS:
            try:
                index = int(message.content) - 1
                self.reason_subtype = self.report_reason.subtypes[index]
            except (ValueError, IndexError):
                return [
                    "Invalid input. Please enter the number corresponding to the specific reason."
                ]

            if not self.reason_subtype.ask_if_user_is_minor:
                return self.ask_for_confirmation()

            self.state = State.AWAITING_MINOR_INDICATION
            return ["Are you a minor? Reply `yes` or `no`."]

        if self.state == State.AWAITING_MINOR_INDICATION:
            self.user_is_minor = message.content.lower() in ["yes", "y"]
            return self.ask_for_confirmation()

        if self.state == State.AWAITING_REPORT_CONFIRMATION:
            if message.content.lower() == "confirm":
                self.state = State.AWAITING_BLOCK_DECISION
                responses = [
                    "We prohibit any form of non-consensual sharing or threat to share sexual content. We \
                        will review the report and remove any content that violates our Community Standards.",
                    "Your report has been submitted. Thank you for helping keep our community safe.\n",
                    "Would you like to block this user to prevent them from messaging you again? Reply `yes` or `no`.",
                ]

                if not self.user_is_minor:
                    responses.pop(0)

                return responses
            elif message.content.lower() == "cancel":
                self.state = State.REPORT_COMPLETE
                return ["Report cancelled."]
            else:
                return ["Invalid input. Please reply `confirm` or `cancel`."]

        if self.state == State.AWAITING_BLOCK_DECISION:
            if message.content.lower() in ["yes", "y"]:
                self.state = State.REPORT_COMPLETE
                return [
                    "User blocked. Thank you again for the report, we will review it and take appropriate action."
                ]
            elif message.content.lower() in ["no", "n"]:
                self.state = State.REPORT_COMPLETE
                return [
                    "Thank you for the report, we will review it and take appropriate action."
                ]
            else:
                return ["Invalid input. Please reply `yes` or `no`."]

    def ask_for_confirmation(self):
        """
        Assembles the report confirmation message and asks the user to confirm.
        Transitions to the AWAITING_REPORT_CONFIRMATION state.
        """
        self.state = State.AWAITING_REPORT_CONFIRMATION

        reply = "Your report is ready to be submitted.\n"
        reply += "To confirm, here are the details of your report:\n"
        reply += "> ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        reply += "> Message: " + self.message.jump_url + "\n"
        reply += "> Reason: " + self.report_reason.name.value + "\n"

        if self.reason_subtype:
            reply += "> Specifics: " + self.reason_subtype.name.value + "\n"

        if self.user_is_minor is not None:
            reply += (
                "> Are you a minor: " + ("Yes" if self.user_is_minor else "No") + "\n"
            )

        reply += "> ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"

        reply += "\nIf this is correct, reply `confirm`. If not, reply `cancel`."
        return ["Thank you.", reply]

    def report_complete(self):
        """
        Checks if the report flow is complete.
        """
        return self.state == State.REPORT_COMPLETE
