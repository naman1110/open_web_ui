import os
import json
from typing import List, Optional
from pydantic import BaseModel

class Pipeline:
    class Valves(BaseModel):
        # Apply this filter to all pipelines/models (we will filter the specific ones in the code)
        pipelines: List[str] = ["*"]
        
        # Determine the execution priority
        priority: int = 0
        
        # Which user roles should be limited? (Keeps admins from being blocked)
        target_user_roles: List[str] = ["user"]
        
        # The exact limits you requested, stored as a JSON string
        # You can edit this directly in the Open WebUI Valves interface later!
        model_limits_json: str = '{"gpt-5-nano-2025-08-07": 10, "Generate Image": 2}'

    def __init__(self):
        self.type = "filter"
        self.name = "Lifetime Model Limit Filter"
        self.valves = self.Valves()
        
        # Set up a persistent file to store the user counts
        # This saves to the same directory as the script so it survives Docker restarts
        self.storage_file = os.path.join(os.path.dirname(__file__), "user_lifetime_usage.json")
        self.usage_data = self._load_data()

    async def on_startup(self):
        print(f"Startup: {self.name} loaded.")

    async def on_shutdown(self):
        print(f"Shutdown: {self.name} stopping.")

    def _load_data(self) -> dict:
        """Loads user interaction history from the local JSON file."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading usage data: {e}")
                return {}
        return {}

    def _save_data(self):
        """Saves user interaction history to the local JSON file."""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.usage_data, f)
        except Exception as e:
            print(f"Error saving usage data: {e}")

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # If no user data is present, allow the request
        if not user:
            return body

        user_role = user.get("role", "user")
        user_id = user.get("id", "default_user")
        model_id = body.get("model", "")

        # 1. Ignore users who are not in the target roles (e.g., allow admins unlimited access)
        if user_role not in self.valves.target_user_roles:
            return body

        # 2. Parse the limits from the Valves settings
        try:
            limits = json.loads(self.valves.model_limits_json)
        except json.JSONDecodeError:
            print(f"[{self.name}] Error: model_limits_json is invalid. Allowing request.")
            return body

        # 3. If the requested model doesn't have a limit, allow the request to pass freely
        if model_id not in limits:
            return body

        max_lifetime_uses = int(limits[model_id])

        # 4. Check the user's history
        if user_id not in self.usage_data:
            self.usage_data[user_id] = {}

        current_uses = self.usage_data[user_id].get(model_id, 0)

        # 5. Enforce the limit
        if current_uses >= max_lifetime_uses:
            raise Exception(
                f"Lifetime limit reached. You can only use the '{model_id}' model a maximum of {max_lifetime_uses} times."
            )

        # 6. Increment their usage and save to the file
        self.usage_data[user_id][model_id] = current_uses + 1
        self._save_data()

        return body
