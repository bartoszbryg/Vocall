import asyncio
import json
from typing import Any

from server.config import settings


class SalesforceTool:
    _instance: Any = None

    @classmethod
    def get_instance(cls) -> Any:
        if cls._instance is None and settings.salesforce_username:
            from simple_salesforce import Salesforce

            cls._instance = Salesforce(
                username=settings.salesforce_username,
                password=settings.salesforce_password,
                security_token=settings.salesforce_security_token,
                domain=settings.salesforce_domain,
            )
        return cls._instance

    @classmethod
    async def query(cls, soql: str) -> dict:
        """Run a SOQL query, return results dict."""
        sf = cls.get_instance()
        if not sf:
            return {"error": "Salesforce not configured"}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, sf.query, soql)
        return result

    @classmethod
    def get_tool_definition(cls) -> dict:
        """Return Anthropic tool schema for Salesforce SOQL query."""
        return {
            "name": "salesforce_query",
            "description": (
                "Query Salesforce CRM using SOQL. Use this to look up contacts, accounts, "
                "opportunities, cases, or any Salesforce object. "
                "Example: SELECT Id, Name, Email FROM Contact WHERE Email = 'john@example.com'"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "soql": {
                        "type": "string",
                        "description": (
                            "The SOQL query to execute. Always use SELECT with specific fields, "
                            "not SELECT *."
                        ),
                    }
                },
                "required": ["soql"],
            },
        }