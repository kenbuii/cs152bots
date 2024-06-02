from enum import Enum, auto
from dataclasses import dataclass
import discord
import re
import json
import os
import aiohttp

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE_LINK = auto()
    AWAITING_REPORT_REASON = auto()
    AWAITING_REASON_SPECIFICS = auto()
    AWAITING_MINOR_INDICATION = auto()
    AWAITING_REPORT_CONFIRMATION = auto()
    AWAITING_BLOCK_DECISION = auto()
    REPORT_COMPLETE = auto()
    PENDING_REVIEW = auto()
    PENDING_NONCONSENSUAL_REVIEW = auto()
    PENDING_NUDITY_REVIEW = auto()
    PENDING_GUIDELINES_REVIEW = auto()
    PENDING_MINOR_REVIEW = auto()
    PENDING_ADVERSARY_REVIEW = auto()
    REVIEW_COMPLETE = auto()


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
    REVIEW_KEYWORD = "review"
    HELP_KEYWORD = "help"
    BACK_KEYWORD = "back"

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

    perspective_api_key = None

    def __init__(self, client, author_id):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.report_reason = None
        self.reason_subtype = None
        self.user_is_minor = None
        self.message_history = None
        self.author_id = author_id
        self.guild = None
        self.previous_state = None
        self.previous_reason = None
        self.previous_subtype = None
        self.previous_minor_indication = None

        self.perspective_client = None
        self.perspective_api_key = None

        token_path = "tokens.json"

        if not os.path.isfile(token_path):
            raise Exception(f"{token_path} not found!")
        with open(token_path) as f:
            tokens = json.load(f)
            self.perspective_api_key = tokens["perspective"]
    
    def __lt__(self, other):
        if self.user_is_minor != other.user_is_minor:
            return self.user_is_minor
        else:
            return self.severity_score > other.severity_score

    async def handle_message(self, message):
        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            self.client.reports.pop(self.author_id)
            return ["Report cancelled."]

        if message.content == self.HELP_KEYWORD:
            return [
                "To report a message:\n"
                "1. Use the `report` command\n"
                "2. Provide the message link when prompted\n"
                "3. Select a report reason from the menu\n"
                "4. Provide specifics and confirm the report\n\n"
                "You can cancel at any time by saying `cancel`.\n"
                "You can go back to the previous step by saying `back`."
            ]

        if message.content == self.BACK_KEYWORD:
            return await self.handle_back()

        if self.state == State.REPORT_START:
            reply = "Thank you for starting the reporting process.\n"
            reply += "You can go back to the previous step by saying `back`. Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.update_previous_state()
            self.state = State.AWAITING_MESSAGE_LINK
            return [reply]

        if self.state == State.AWAITING_MESSAGE_LINK:
            m = re.search("/(\d+)/(\d+)/(\d+)", message.content)
            if not m:
                return [
                    "I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."
                ]
            guild = self.client.get_guild(int(m.group(1)))
            self.guild = guild
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
                await self.set_severity_score()
            except discord.errors.NotFound:
                return [
                    "It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."
                ]

            self.message_history = [
                m
                async for m in self.message.channel.history(
                    around=self.message, limit=15
                )
            ]
            self.message_history = sorted(self.message_history, key=lambda m: m.created_at)

            self.update_previous_state()
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

            self.update_previous_state()
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

            self.update_previous_state()
            self.state = State.AWAITING_MINOR_INDICATION
            return ["Are you a minor? Reply `yes` or `no`."]

        if self.state == State.AWAITING_MINOR_INDICATION:
            self.user_is_minor = message.content.lower() in ["yes", "y"]
            return self.ask_for_confirmation()

        if self.state == State.AWAITING_REPORT_CONFIRMATION:
            if message.content.lower() == "confirm":
                self.update_previous_state()
                self.state = State.AWAITING_BLOCK_DECISION
                responses = [
                    "Your report has been submitted. We will review the report and remove any content that "
                    "violates our Community Standards. Thank you for keeping our community safe.",
                    "Would you like to block this user to prevent them from messaging you again? Reply `yes` or `no`.",
                ]

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

    async def handle_review(self, message):
        if message.content == self.BACK_KEYWORD:
            return await self.handle_review_back()

        if self.state == State.REPORT_COMPLETE:
            reply = "Thank you for starting the review process.\n"
            reply += "Here are the details of the report:\n"
            reply += "> ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            reply += "> Message: " + self.message.jump_url + "\n"
            reply += f"> Message Author: <@{self.message.author.id}> \n"
            reply += "> Message Contents: " + self.message.content + "\n"
            reply += "> Reason: " + self.report_reason.name.value + "\n"

            if self.reason_subtype:
                reply += "> Specifics: " + self.reason_subtype.name.value + "\n"

            if self.user_is_minor is not None:
                reply += "> Minor: " + ("Yes" if self.user_is_minor else "No") + "\n"
            reply += "> ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            reply += "Is there a threat of nonconsensual sharing of intimate or sexually explicit content?\n"
            reply += "Reply `yes` or `no`."
            self.update_previous_state()
            self.state = State.PENDING_NONCONSENSUAL_REVIEW
            return [reply]
        if self.state == State.PENDING_NONCONSENSUAL_REVIEW:
            if message.content.lower() in ["yes", "y"]:
                reply = "I understand. Does the reported content contain nudity?\n"
                reply += "Reply `yes` or `no`."
                self.update_previous_state()
                self.state = State.PENDING_NUDITY_REVIEW
                return [reply]
            elif message.content.lower() in ["no", "n"]:
                reply = "I understand. Does the reported content violate platform guidelines?\n"
                reply += "Reply `yes` or `no`."
                self.update_previous_state()
                self.state = State.PENDING_GUIDELINES_REVIEW
                return [reply]
            else:
                return ["Invalid input. Please reply `yes` or `no`."]
        if self.state == State.PENDING_NUDITY_REVIEW:
            if message.content.lower() in ["yes", "y"]:
                reply = "Thank you for reviewing the report. The reported content contains nudity and has been removed.\n"
                await self.message.delete()
                reply += "Is the reporting user a minor?\n"
                reply += "Reply `yes` or `no`."
                self.update_previous_state()
                self.state = State.PENDING_MINOR_REVIEW
                return [reply]
            elif message.content.lower() in ["no", "n"]:
                reply = "Thank you for reviewing the report. The reported content does not contain nudity.\n"
                reply += "Is the reporting user a minor?\n"
                reply += "Reply `yes` or `no`."
                self.update_previous_state()
                self.state = State.PENDING_MINOR_REVIEW
                return [reply]
            else:
                return ["Invalid input. Please reply `yes` or `no`."]
        if self.state == State.PENDING_MINOR_REVIEW:
            if message.content.lower() in ["yes", "y"]:
                reply = "Thank you for reviewing the report. The reported content does involve a minor. This review is now marked as completed.\n"
                reply += "Please file a report with the National Center for Missing and Exploited Children at https://report.cybertip.org/.\n"
                reply += (
                    "Please file a report with your local law enforcement agency.\n"
                )
                reply += f"<@{self.message.author.id}> has been banned."
                self.state = State.REVIEW_COMPLETE
                return [reply]
            elif message.content.lower() in ["no", "n"]:
                reply = "Thank you for your cooperation. The reported content does not involve a minor. This review is now marked as completed.\n"
                reply += (
                    "Please file a report with your local law enforcement agency.\n"
                )
                reply += f"<@{self.message.author.id}> has been banned."
                self.state = State.REVIEW_COMPLETE
                return [reply]
            else:
                return ["Invalid input. Please reply `yes` or `no`."]
        if self.state == State.PENDING_GUIDELINES_REVIEW:
            if message.content.lower() in ["yes", "y"]:
                reply = "Thank you for reviewing the report. The reported content violates platform guidelines. Please report to Discord. This review is now marked as completed.\n"
                self.state = State.REVIEW_COMPLETE
                return [reply]
            elif message.content.lower() in ["no", "n"]:
                reply = "Does this look like adversarial reporting?\n"
                reply += "Reply `yes` or `no`."
                self.update_previous_state()
                self.state = State.PENDING_ADVERSARY_REVIEW
                return [reply]
            else:
                return ["Invalid input. Please reply `yes` or `no`."]
        if self.state == State.PENDING_ADVERSARY_REVIEW:
            if message.content.lower() in ["yes", "y"]:
                reply = "Thank you for reviewing the report. The user will be temporarily banned from reporting. This review is now marked as completed.\n"
                self.client.report_ban.append(self.author_id)
                self.state = State.REVIEW_COMPLETE
                return [reply]
            elif message.content.lower() in ["no", "n"]:
                reply = "This review is now marked as completed.\n"
                self.state = State.REVIEW_COMPLETE
                return [reply]
            else:
                return ["Invalid input. Please reply `yes` or `no`."]

    async def handle_back(self):
        if self.previous_state is None:
            return ["There is no previous step to go back to."]

        self.state = self.previous_state
        self.report_reason = self.previous_reason
        self.reason_subtype = self.previous_subtype
        self.user_is_minor = self.previous_minor_indication

        if self.state == State.AWAITING_MESSAGE_LINK:
            self.previous_state = None
            return ["Please provide the message link again."]
        elif self.state == State.AWAITING_REPORT_REASON:
            self.previous_state = State.AWAITING_MESSAGE_LINK
            return ["Please select the report reason again."]
        elif self.state == State.AWAITING_REASON_SPECIFICS:
            self.previous_state = State.AWAITING_REPORT_REASON
            return ["Please select the specific reason again."]
        elif self.state == State.AWAITING_MINOR_INDICATION:
            self.previous_state = State.AWAITING_REASON_SPECIFICS
            return ["Please indicate if you are a minor again."]
        elif self.state == State.AWAITING_REPORT_CONFIRMATION:
            if self.reason_subtype and self.reason_subtype.ask_if_user_is_minor:
                self.previous_state = State.AWAITING_MINOR_INDICATION
            else:
                self.previous_state = State.AWAITING_REASON_SPECIFICS
            return ["Please confirm your report again."]

    async def handle_review_back(self):
        if self.state == State.PENDING_NONCONSENSUAL_REVIEW:
            self.state = State.REPORT_COMPLETE
            return ["Please review the report details again."]
        elif self.state == State.PENDING_NUDITY_REVIEW:
            self.state = State.PENDING_NONCONSENSUAL_REVIEW
            return [
                "Please indicate if there is a threat of nonconsensual sharing again."
            ]
        elif self.state == State.PENDING_MINOR_REVIEW:
            self.state = State.PENDING_NUDITY_REVIEW
            return ["Please indicate if the reported content contains nudity again."]
        elif self.state == State.PENDING_GUIDELINES_REVIEW:
            self.state = State.PENDING_NONCONSENSUAL_REVIEW
            return [
                "Please indicate if there is a threat of nonconsensual sharing again."
            ]
        elif self.state == State.PENDING_ADVERSARY_REVIEW:
            self.state = State.PENDING_GUIDELINES_REVIEW
            return [
                "Please indicate if the reported content violates platform guidelines again."
            ]
        else:
            return ["There is no previous step to go back to."]

    def ask_for_confirmation(self):
        """
        Assembles the report confirmation message and asks the user to confirm.
        Transitions to the AWAITING_REPORT_CONFIRMATION state.
        """
        self.update_previous_state()
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
    
    async def set_severity_score(self):
        if not self.perspective_client:
            self.perspective_client = aiohttp.ClientSession()

        perspective_url = f'https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_api_key}'
        
        perspective_request = {
            'comment': {'text': self.message.content},
            'requestedAttributes': {
                'TOXICITY': {},
                'SEVERE_TOXICITY': {},
                'IDENTITY_ATTACK': {},
                'INSULT': {},
                'THREAT': {},
            },
        }
        
        async with self.perspective_client.post(perspective_url, json=perspective_request) as response:
            perspective_data = await response.json()

        attribute_scores = perspective_data.get('attributeScores', {})
        self.severity_score = (
            attribute_scores.get('TOXICITY', {}).get('summaryScore', {}).get('value', 0) * 0.15 +
            attribute_scores.get('SEVERE_TOXICITY', {}).get('summaryScore', {}).get('value', 0) * 0.15 +
            attribute_scores.get('IDENTITY_ATTACK', {}).get('summaryScore', {}).get('value', 0) * 0.15 +
            attribute_scores.get('INSULT', {}).get('summaryScore', {}).get('value', 0) * 0.05 +
            attribute_scores.get('THREAT', {}).get('summaryScore', {}).get('value', 0) * 0.5
        )

        print(f'set severity score of {self.severity_score} for message "{self.message.content}"')
    
    @classmethod
    async def load_with_openai_client(cls, client, reporter_id, message, message_history):
        report = cls(client, reporter_id)
        
        report.message = message
        report.message_history = message_history
        await report.set_severity_score()
        
        # Format the message history for context
        formatted_history = "\n".join(
            [f"{m.author.name}: {m.content}" for m in report.message_history]
        )
        
        reason_response = client.openai_client.chat.completions.create(
            model=client.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a Discord moderation bot that helps users report messages. Based on the provided message history, determine the most appropriate report reason from the available options. Respond with a JSON object containing the 'reason' field."},
                {"role": "user", "content": formatted_history},
                {"role": "user", "content": f"What is the most appropriate report reason for the last message? Choose from the following options: {', '.join([r.name.value for r in cls.REPORT_REASON_INFOS])}. Respond with a JSON object in the format: {{\"reason\": \"<selected_reason>\"}}"}
            ]
        )
        reason_data = json.loads(reason_response.choices[0].message.content.strip())
        print(f'Reason: {reason_data}')
        report.report_reason = next((r for r in cls.REPORT_REASON_INFOS if r.name.value == reason_data["reason"]), None)
        print(report.report_reason)
        print()
        
        if report.report_reason and report.report_reason.subtypes:
            subtype_response = client.openai_client.chat.completions.create(
                model=client.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a Discord moderation bot that helps users report messages. Based on the provided message history and report reason, determine the most appropriate specific reason from the available options. Respond with a JSON object containing the 'subtype' field."},
                    {"role": "user", "content": formatted_history},
                    {"role": "user", "content": f"The report reason is {report.report_reason.name.value}. What is the most appropriate specific reason? Choose from the following options: {', '.join([s.name.value for s in report.report_reason.subtypes])}. Respond with a JSON object in the format: {{\"subtype\": \"<selected_subtype>\"}}"}
                ]
            )
            
            subtype_data = json.loads(subtype_response.choices[0].message.content.strip())
            print(f'Subtype: {subtype_data}')
            
            report.reason_subtype = next((s for s in report.report_reason.subtypes if s.name.value == subtype_data["subtype"]), None)
            print(report.reason_subtype)
            print()
        
        report.state = State.REPORT_COMPLETE
        
        return report

    def update_previous_state(self):
        self.previous_state = self.state
        self.previous_reason = self.report_reason
        self.previous_subtype = self.reason_subtype
        self.previous_minor_indication = self.user_is_minor

    def review_complete(self):
        """
        Checks if the review flow is complete.
        """
        return self.state == State.REVIEW_COMPLETE

    def report_complete(self):
        """
        Checks if the report flow is complete.
        """
        return self.state == State.REPORT_COMPLETE
