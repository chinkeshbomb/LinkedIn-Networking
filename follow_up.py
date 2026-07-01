"""LinkedIn Follow-Up Message Handler."""

import asyncio
import json
import random
import logging
from datetime import datetime

from playwright.async_api import Page, BrowserContext

import config
from automator import (
    get_browser_context,
    check_login,
    human_delay,
    load_data,
    save_data,
)

logger = logging.getLogger(__name__)


async def check_for_replies(page: Page, profile_url: str, name: str) -> bool:
    """
    Check if the person has replied to our last message.
    Navigate to the conversation and check if their last message is after ours.
    Returns True if they replied (meaning we should NOT auto-follow-up).
    """
    try:
        # Navigate to messaging and search for the person
        await page.goto(config.LINKEDIN_MESSAGING, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Search for the conversation
        search_input = await page.query_selector(
            "input[placeholder*='Search messages'], "
            "input.msg-search-form__search-field"
        )
        if search_input:
            await search_input.click()
            await asyncio.sleep(0.5)
            # Type first name to find conversation
            first_name = name.split(" ")[0]
            await search_input.fill("")
            await search_input.type(first_name, delay=random.randint(50, 100))
            await asyncio.sleep(2)

            # Click on the conversation if found
            conv_item = await page.query_selector(
                f"li.msg-conversation-listitem:has-text('{first_name}')"
            )
            if conv_item:
                await conv_item.click()
                await asyncio.sleep(2)

                # Check the last message sender
                # Get all message items
                messages = await page.query_selector_all(
                    ".msg-s-message-list__event"
                )
                if messages:
                    last_msg = messages[-1]
                    # Check if the last message is from them (not us)
                    sender = await last_msg.query_selector(
                        ".msg-s-message-group__profile-link, "
                        ".msg-s-message-group__name"
                    )
                    if sender:
                        sender_text = await sender.inner_text()
                        # If last message is NOT from us, they replied
                        if first_name.lower() in sender_text.lower():
                            logger.info(f"{name} has replied - skipping follow-up")
                            return True

        return False
    except Exception as e:
        logger.warning(f"Error checking replies for {name}: {e}")
        return False


async def send_follow_up_message(
    page: Page, profile_url: str, name: str, message: str
) -> bool:
    """
    Send a follow-up message to an accepted connection.
    """
    try:
        # Go to the person's profile
        await page.goto(profile_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Find the Message button
        msg_btn = await page.query_selector(
            "button[aria-label*='Message'], "
            "a[href*='messaging']:text-is('Message'), "
            "button:text-is('Message')"
        )

        if not msg_btn:
            logger.warning(f"No Message button found for {name} - might not be connected")
            return False

        await msg_btn.click()
        await asyncio.sleep(2)

        # Wait for message dialog
        msg_input = await page.wait_for_selector(
            "div[role='textbox'][aria-label*='message'], "
            "div.msg-form__contenteditable, "
            "div[contenteditable='true'].msg-form__contenteditable",
            timeout=5000,
        )

        if not msg_input:
            logger.warning(f"Message input not found for {name}")
            return False

        # Personalize and type message
        personalized_msg = message.replace("{name}", name.split(" ")[0])

        await msg_input.click()
        await asyncio.sleep(0.5)

        # Type like a human
        for char in personalized_msg:
            await msg_input.type(char, delay=random.randint(30, 80))
            if random.random() < 0.03:
                await asyncio.sleep(random.uniform(0.5, 1.2))

        await human_delay(1, 3)

        # Send
        send_btn = await page.query_selector(
            "button[type='submit'].msg-form__send-button, "
            "button.msg-form__send-button, "
            "button[aria-label='Send']"
        )

        if send_btn:
            await send_btn.click()
            await human_delay(2, 4)
            logger.info(f"Follow-up sent to {name}")
            return True
        else:
            # Try keyboard shortcut
            await page.keyboard.press("Enter")
            await human_delay(2, 4)
            logger.info(f"Follow-up sent to {name} (Enter key)")
            return True

    except Exception as e:
        logger.error(f"Error sending follow-up to {name}: {e}")
        return False
    finally:
        # Close message dialog if open
        try:
            close_btn = await page.query_selector(
                "button[data-control-name='overlay.close_conversation_window'], "
                "button[aria-label='Close your conversation']"
            )
            if close_btn:
                await close_btn.click()
        except Exception:
            pass


async def run_follow_ups(
    stage: int,
    message_template: str,
    status_callback=None,
):
    """
    Send follow-up messages to accepted connections.
    
    Args:
        stage: 1, 2, or 3 (which follow-up stage)
        message_template: Message to send (use {name} for personalization)
        status_callback: Function to call with status updates
    """
    data = load_data()
    context = await get_browser_context()
    page = await context.new_page()
    sent_count = 0
    skipped_count = 0

    try:
        is_logged_in = await check_login(page)
        if not is_logged_in:
            msg = "Not logged in. Please log in first."
            if status_callback:
                status_callback(msg)
            return {"status": "not_logged_in", "sent": 0, "message": msg}

        if status_callback:
            status_callback(f"Starting follow-up stage {stage}...")

        # Get connections that:
        # 1. Have been sent a connection request
        # 2. Haven't received this stage of follow-up yet
        connections_sent = data.get("connections_sent", [])
        follow_ups_done = data.get("follow_ups", [])

        # Find who already got this stage
        already_followed_up = set()
        for fu in follow_ups_done:
            if fu.get("stage") == stage:
                already_followed_up.add(fu["profile_url"])

        candidates = [
            c for c in connections_sent
            if c["profile_url"] not in already_followed_up
            and c.get("status") == "pending"  # Only pending (assumed accepted if we can message)
        ]

        if status_callback:
            status_callback(f"Found {len(candidates)} candidates for stage {stage} follow-up")

        for person in candidates:
            name = person["name"]
            profile_url = person["profile_url"]

            if status_callback:
                status_callback(f"Checking {name}...")

            # Check if they replied - if so, skip
            has_replied = await check_for_replies(page, profile_url, name)
            if has_replied:
                skipped_count += 1
                # Update status
                person["status"] = "replied"
                save_data(data)
                if status_callback:
                    status_callback(f"{name} has replied - skipping")
                continue

            # Try sending follow-up
            success = await send_follow_up_message(
                page, profile_url, name, message_template
            )

            if success:
                sent_count += 1
                data["follow_ups"].append({
                    "profile_url": profile_url,
                    "name": name,
                    "message": message_template.replace("{name}", name.split(" ")[0]),
                    "stage": stage,
                    "date_sent": str(datetime.now()),
                })
                save_data(data)

                if status_callback:
                    status_callback(f"Follow-up stage {stage} sent to {name}")
            else:
                skipped_count += 1
                if status_callback:
                    status_callback(f"Could not message {name} (not connected yet?)")

            # Human-like delay
            await human_delay(
                config.MIN_DELAY_BETWEEN_REQUESTS,
                config.MAX_DELAY_BETWEEN_REQUESTS,
            )

    except Exception as e:
        logger.error(f"Follow-up error: {e}")
        if status_callback:
            status_callback(f"Error: {e}")
    finally:
        await page.close()
        await context.close()

    result = {
        "status": "completed",
        "sent": sent_count,
        "skipped": skipped_count,
        "message": f"Follow-up stage {stage}: sent {sent_count}, skipped {skipped_count}.",
    }
    logger.info(f"Follow-up result: {result}")
    return result
