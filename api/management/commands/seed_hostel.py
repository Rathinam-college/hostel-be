import os
import bcrypt
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from api.models import (
    Hostel, Room, Bed, Resident, Institute, SharingType,
    ExitReason, Allocation, Renewal, Requirement, ConstructionPhase, User
)

from api.views import init_db_schema

class Command(BaseCommand):
    help = 'Runs the PostgreSQL DDL schema and populates seed data from Image 2 ERD diagram'

    def handle(self, *args, **kwargs):
        self.stdout.write("Running PostgreSQL DDL Schema Initializer for pgAdmin...")
        response = init_db_schema(None)
        if response.status_code == 200:
            self.stdout.write(self.style.SUCCESS("Database schema & normalized tables created successfully! Visible in pgAdmin."))
        else:
            self.stdout.write(self.style.ERROR(f"Database schema initialization output: {response.content.decode('utf-8')}"))

