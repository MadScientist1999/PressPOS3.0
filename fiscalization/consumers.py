# messaging/consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
import json
from asgiref.sync import sync_to_async
import datetime
from django.db import models
from .signals import submitAll
from .models import FiscalBranch



class SubmitConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.user_group_name = None   # make sure it always exists
        
        if user.is_anonymous:
            print("User is anonymous, closing connection.")
            await self.close()
        else:
            self.user_group_name = f"user_{user.id}"
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            await self.accept()

    async def disconnect(self, close_code):
        if self.user_group_name:   # only discard if it was set
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive(self,branch_info):
     from asgiref.sync import sync_to_async
     user = self.scope["user"]
     branch_id=json.loads(branch_info).get("id")
     branch=FiscalBranch.objects.get(id=branch_id)
       
     if user.is_anonymous:
        return
      
     try:
        # This is enough
        await sync_to_async(submitAll, thread_sensitive=True
        )(branch=branch)
     except Exception as e:
        print(str(e))
        print("Failed to save message:", e)
     

     # 3️⃣ Optionally echo the message back to sender
     await self.channel_layer.group_send(
            f"user_{user.id}",
            {
        "received":True
      }    
    )

   
