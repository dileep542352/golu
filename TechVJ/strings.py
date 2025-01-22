HELP_TXT = """
**Welcome to the Bot!**

Here are the available commands:

- **/start**: Start the bot.
- **/help**: Show this help message.
- **/batch**: Process a batch of messages.
  Example: `/batch 100-110`

**BATCH COMMAND**

To use the batch command, send a message in the following format:
`/batch <start_message_id>-<end_message_id>`

Example:
`/batch 100-110`

This will process messages from ID 100 to 110.
"""

BATCH_TXT = """
**Batch Processing Started!**

Processing messages from ID `{}` to `{}`.
"""
