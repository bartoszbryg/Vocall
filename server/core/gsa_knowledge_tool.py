"""
GSA Knowledge Tool — queries the GatewayGSA SQLite database directly.

GatewayGSA schema (v2):
  knowledge_items  — FAQs, resources, policies (FTS5 via knowledge_fts)
  events           — GSA events with date/time/location
  organizations    — org hierarchy (contacts stored as knowledge_items of type 'contact')
  settings         — per-org key/value config

FTS virtual table: knowledge_fts(search_text) — content='knowledge_items', content_rowid='id'
"""

import asyncio
import json
import sqlite3
from datetime import date
from pathlib import Path

from server.config import settings


_NO_DB_MSG = (
    "Knowledge base not connected — please set GSA_DB_PATH to the "
    "GatewayGSA SQLite file path."
)

MOCK_KNOWLEDGE = [
    {
        "category": "funding",
        "question": "How do I apply for a GSA travel grant?",
        "answer": "Submit a travel grant application through the GSA portal at least 3 weeks before your trip. You'll need a conference acceptance letter, cost estimate, and faculty advisor approval. Awards are up to $500 for domestic and $1000 for international travel. The deadline is the 15th of each month."
    },
    {
        "category": "funding",
        "question": "What funding opportunities does GSA offer?",
        "answer": "GSA offers travel grants for conferences, research grants up to $1500, and professional development funding for workshops and certifications. Applications open at the start of each semester. Contact funding@gsa.njit.edu for details."
    },
    {
        "category": "funding",
        "question": "When is the travel grant deadline?",
        "answer": "Travel grant applications are due on the 15th of each month. Late applications are not accepted. Results are announced within 2 weeks of the deadline."
    },
    {
        "category": "events",
        "question": "What events does GSA have coming up?",
        "answer": "Upcoming GSA events include the Graduate Research Symposium on March 15th in Campus Center Room 240, a Professional Networking Night on March 22nd, and the Spring Social on April 5th at the GSA lounge. Check the GSA website for the full calendar."
    },
    {
        "category": "events",
        "question": "When is the next GSA meeting?",
        "answer": "GSA general body meetings are held every second Tuesday of the month at 5 PM in Kupfrian Hall Room 104. All graduate students are welcome to attend."
    },
    {
        "category": "events",
        "question": "Does GSA organize social events?",
        "answer": "Yes, GSA organizes monthly socials, game nights, cultural celebrations, and outdoor trips. These are free for all graduate students. Follow @njitgsa on Instagram for announcements."
    },
    {
        "category": "membership",
        "question": "How do I join GSA?",
        "answer": "All NJIT graduate students are automatically members of GSA. You can get more involved by attending general body meetings, joining a committee, or running for an officer position during elections in April."
    },
    {
        "category": "membership",
        "question": "How do I become a GSA officer?",
        "answer": "GSA officer elections are held every April. To run, you must be a full-time graduate student in good standing with at least one semester remaining. Nomination forms are available on the GSA website two weeks before elections."
    },
    {
        "category": "resources",
        "question": "What academic resources does GSA provide?",
        "answer": "GSA provides a study room in Campus Center Room 235 available 24/7 with your NJIT ID, a graduate student lounge with free coffee and printing, and free tutoring coordination through the Graduate Academic Success office."
    },
    {
        "category": "resources",
        "question": "Does GSA have a food pantry or emergency resources?",
        "answer": "Yes, NJIT has a food pantry in the Student Mall open Monday through Friday. GSA also has an emergency fund for students facing unexpected financial hardship. Email president@gsa.njit.edu for emergency assistance."
    },
    {
        "category": "resources",
        "question": "Where is the GSA office?",
        "answer": "The GSA office is located in Campus Center Room 235. Office hours are Monday through Friday from 10 AM to 4 PM. You can also reach us at gsa@njit.edu or call 973-596-3466."
    },
    {
        "category": "contacts",
        "question": "Who do I contact for GSA questions?",
        "answer": "For general questions email gsa@njit.edu. For funding questions contact funding@gsa.njit.edu. For events contact events@gsa.njit.edu. The GSA president can be reached at president@gsa.njit.edu."
    },
    {
        "category": "contacts",
        "question": "Who is the current GSA president?",
        "answer": "The current GSA president can be reached at president@gsa.njit.edu. Officer information is updated each May after elections on the GSA website at gsa.njit.edu."
    },
    {
        "category": "housing",
        "question": "Does GSA help with housing?",
        "answer": "GSA maintains a housing board on its website where students can post and find roommate listings. For official on-campus housing, contact NJIT Housing at housing@njit.edu. GSA also holds a housing fair each August before the fall semester."
    },
    {
        "category": "healthcare",
        "question": "What health insurance options do graduate students have?",
        "answer": "Full-time graduate students are eligible for the NJIT student health insurance plan through Aetna. Enrollment is during the first two weeks of each semester. Graduate assistants receive subsidized coverage. Visit the Student Health Center in Fenster Hall for details."
    },
    {
        "category": "international",
        "question": "What support does GSA offer international students?",
        "answer": "GSA has an International Student Committee that organizes cultural events, visa information sessions, and connects new international students with mentors. Contact international@gsa.njit.edu or visit the International Student Services office in Campbell Hall."
    },
]


class GSAKnowledgeTool:

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection | None:
        """Connect to GatewayGSA's SQLite DB. Returns None if unavailable."""
        db_path = settings.gsa_db_path
        if not db_path or not Path(db_path).exists():
            return None
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Sync helpers (run in executor to keep async callers non-blocking)
    # ------------------------------------------------------------------

    @classmethod
    def _search_mock(cls, query: str, category: str = "all") -> str:
        """Search mock knowledge base using simple keyword matching."""
        query_lower = query.lower()
        results = []

        for item in MOCK_KNOWLEDGE:
            if category != "all" and item["category"] != category:
                continue
            # Score by keyword overlap
            score = sum(1 for word in query_lower.split()
                       if len(word) > 3 and word in item["question"].lower() + " " + item["answer"].lower())
            if score > 0:
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        top = results[:3]

        if not top:
            return "No specific information found in the knowledge base for that query."

        output = []
        for _, item in top:
            output.append(f"Q: {item['question']}\nA: {item['answer']}")

        return "\n\n".join(output)

    @classmethod
    def _sync_search(cls, query: str, category: str) -> str:
        conn = cls._get_conn()
        if conn is None:
            return cls._search_mock(query, category)

        results: list[dict] = []

        try:
            with conn:
                if category in ("all", "faqs", "resources"):
                    # FTS5 search on knowledge_items
                    types_filter = ""
                    params: list = [query]
                    if category == "faqs":
                        types_filter = "AND ki.type = 'faq'"
                    elif category == "resources":
                        types_filter = "AND ki.type = 'resource'"

                    rows = conn.execute(
                        f"""
                        SELECT ki.id, ki.type, ki.title, ki.content, ki.metadata
                        FROM knowledge_fts AS fts
                        JOIN knowledge_items AS ki ON ki.id = fts.rowid
                        WHERE fts.search_text MATCH ?
                          AND ki.is_active = 1
                          {types_filter}
                        ORDER BY rank
                        LIMIT 5
                        """,
                        params,
                    ).fetchall()

                    for r in rows:
                        results.append({
                            "source": "knowledge_base",
                            "type": r["type"],
                            "title": r["title"] or "",
                            "content": r["content"],
                        })

                if category in ("all", "events"):
                    today = date.today().isoformat()
                    rows = conn.execute(
                        """
                        SELECT name, date, time, location, description,
                               organizer, rsvp_link, category
                        FROM events
                        WHERE date >= ?
                          AND (
                              name LIKE '%' || ? || '%'
                              OR description LIKE '%' || ? || '%'
                              OR category LIKE '%' || ? || '%'
                          )
                        ORDER BY date ASC
                        LIMIT 5
                        """,
                        (today, query, query, query),
                    ).fetchall()

                    for r in rows:
                        results.append({
                            "source": "events",
                            "type": "event",
                            "title": r["name"],
                            "content": (
                                f"Date: {r['date']} {r['time']} | "
                                f"Location: {r['location']} | "
                                f"{r['description']}"
                            ),
                            "rsvp_link": r["rsvp_link"],
                        })

                if category in ("all", "contacts"):
                    rows = conn.execute(
                        """
                        SELECT ki.title, ki.content, ki.metadata
                        FROM knowledge_items ki
                        WHERE ki.type = 'contact'
                          AND ki.is_active = 1
                          AND (
                              ki.title LIKE '%' || ? || '%'
                              OR ki.content LIKE '%' || ? || '%'
                          )
                        LIMIT 5
                        """,
                        (query, query),
                    ).fetchall()

                    for r in rows:
                        results.append({
                            "source": "contacts",
                            "type": "contact",
                            "title": r["title"] or "",
                            "content": r["content"],
                        })

        finally:
            conn.close()

        if not results:
            return json.dumps({"results": [], "message": "No results found for that query."})

        return json.dumps({"results": results})

    @classmethod
    def _sync_upcoming_events(cls) -> str:
        conn = cls._get_conn()
        if conn is None:
            return """Upcoming GSA Events:
- Graduate Research Symposium: March 15th, Campus Center Room 240, 2-5 PM
- Professional Networking Night: March 22nd, Campus Center Ballroom, 6-8 PM
- General Body Meeting: April 8th, Kupfrian Hall Room 104, 5 PM
- Spring Social: April 5th, GSA Lounge, 7-10 PM
- Housing Fair: August 20th, Campus Center Atrium, 10 AM-3 PM"""

        today = date.today().isoformat()
        try:
            with conn:
                rows = conn.execute(
                    """
                    SELECT name, date, time, location, description,
                           organizer, rsvp_link, category
                    FROM events
                    WHERE date >= ?
                    ORDER BY date ASC
                    LIMIT 10
                    """,
                    (today,),
                ).fetchall()
        finally:
            conn.close()

        if not rows:
            return json.dumps({"events": [], "message": "No upcoming events found."})

        events = [
            {
                "name": r["name"],
                "date": r["date"],
                "time": r["time"],
                "location": r["location"],
                "description": r["description"],
                "organizer": r["organizer"],
                "rsvp_link": r["rsvp_link"],
                "category": r["category"],
            }
            for r in rows
        ]
        return json.dumps({"events": events})

    @classmethod
    def _sync_contacts(cls) -> str:
        conn = cls._get_conn()
        if conn is None:
            return """GSA Contacts:
- General inquiries: gsa@njit.edu
- Funding & grants: funding@gsa.njit.edu
- Events: events@gsa.njit.edu
- International students: international@gsa.njit.edu
- President: president@gsa.njit.edu
- Office: Campus Center Room 235, Mon-Fri 10AM-4PM
- Phone: 973-596-3466"""

        try:
            with conn:
                rows = conn.execute(
                    """
                    SELECT ki.title, ki.content, ki.metadata
                    FROM knowledge_items ki
                    WHERE ki.type = 'contact'
                      AND ki.is_active = 1
                    ORDER BY ki.title ASC
                    LIMIT 20
                    """,
                ).fetchall()
        finally:
            conn.close()

        if not rows:
            # Fallback: return generic GSA email
            return json.dumps({
                "contacts": [],
                "message": "No specific contacts found. Reach GSA at gsa@njit.edu",
            })

        contacts = [
            {
                "name": r["title"] or "",
                "info": r["content"],
            }
            for r in rows
        ]
        return json.dumps({"contacts": contacts})

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    @classmethod
    async def search(cls, query: str, category: str = "all") -> str:
        """Search GatewayGSA knowledge base using FTS5 and event/contact queries."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, cls._sync_search, query, category)

    @classmethod
    async def get_upcoming_events(cls) -> str:
        """Return upcoming GSA events as JSON."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, cls._sync_upcoming_events)

    @classmethod
    async def get_contacts(cls) -> str:
        """Return GSA officer contact information as JSON."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, cls._sync_contacts)

    # ------------------------------------------------------------------
    # Anthropic tool definitions
    # ------------------------------------------------------------------

    @classmethod
    def get_tool_definitions(cls) -> list[dict]:
        """Return Anthropic tool schemas for all GSA tools."""
        return [
            {
                "name": "search_gsa_knowledge",
                "description": (
                    "Search the NJIT GSA knowledge base for information about events, "
                    "funding opportunities, policies, campus resources, and frequently "
                    "asked questions. Use this for any student question about GSA."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "The search query — e.g. 'travel funding deadline', "
                                "'how to join GSA', 'upcoming events'"
                            ),
                        },
                        "category": {
                            "type": "string",
                            "enum": ["all", "events", "faqs", "resources", "contacts"],
                            "description": (
                                "Narrow search to a specific category, "
                                "or 'all' to search everything"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_upcoming_events",
                "description": (
                    "Get a list of upcoming GSA events. "
                    "Use when a student asks what events are coming up."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "get_gsa_contacts",
                "description": (
                    "Get GSA officer contact information. Use when a student needs "
                    "to reach a specific GSA officer or department."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]