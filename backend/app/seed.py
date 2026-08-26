"""
Seeds the database with data that matches the mock data already in the
frontend prototype (same coordinates, same incidents/events), so when you
point the frontend at this API instead of its hardcoded arrays, the map
looks the same as what you've already been reviewing.

Run with:  python -m app.seed
"""
import datetime

from app.database import Base, SessionLocal, engine
from app import models, security

Base.metadata.create_all(bind=engine)
db = SessionLocal()

def get_or_create_demo_user():
    user = db.query(models.User).filter(models.User.email == "kris@example.com").first()
    if user:
        return user
    user = models.User(
        username="kris",
        email="kris@example.com",
        password_hash=security.hash_password("password123"),
        phone_verified=True,
        trust_score=82,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def days_ago(n, hours=0):
    return datetime.datetime.utcnow() - datetime.timedelta(days=n, hours=hours)


def seed_incidents(user):
    if db.query(models.Incident).count() > 0:
        print("Incidents already seeded, skipping.")
        return

    rows = [
        dict(category="shooting", severity="high", verified=True, confirms=9, denies=0,
             description="Reports of gunfire near Elm & 8th. Multiple 911 calls, area cordoned off.",
             lat=40.7465, lng=-73.9840, created_at=days_ago(0, hours=0.25)),
        dict(category="accident", severity="med", verified=True, confirms=14, denies=0,
             description="Multi-car collision on Route 9 northbound, right lane blocked.",
             lat=40.7395, lng=-73.9910, created_at=days_ago(0, hours=0.7)),
        dict(category="protest", severity="low", verified=True, confirms=22, denies=0,
             description="Peaceful demonstration gathering outside City Hall, ~200 people.",
             lat=40.7510, lng=-73.9825, created_at=days_ago(0, hours=1)),
        dict(category="fire", severity="high", verified=False, confirms=3, denies=0,
             description="Structure fire reported at a warehouse on Dock St, smoke visible for blocks.",
             lat=40.7360, lng=-73.9950, created_at=days_ago(0, hours=2)),
        dict(category="weather", severity="med", verified=True, confirms=31, denies=0,
             description="Flash flood warning issued for low-lying areas near the river.",
             lat=40.7300, lng=-74.0000, created_at=days_ago(0, hours=3)),
    ]

    # A handful of older incidents around the same mock "areas" the frontend
    # uses (Downtown, Riverside, Uptown, Harbor, Old Mill) spread across the
    # last year, so /areas/insights has something real to compute a trend from.
    import random
    random.seed(7)
    areas = [
        (40.7580, -73.9855, "Downtown", 26),      # rising trend
        (40.7490, -73.9680, "Riverside", 10),      # falling trend
        (40.7720, -73.9560, "Uptown", 16),
        (40.7020, -74.0130, "Harbor", 30),         # rising trend
        (40.7350, -73.9990, "Old Mill", 8),
    ]
    cats = ["accident", "shooting", "protest", "fire", "weather"]
    for base_lat, base_lng, _name, count in areas:
        for i in range(count):
            age_days = random.randint(0, 360)
            rows.append(dict(
                category=random.choice(cats),
                severity=random.choice(["low", "med", "high"]),
                verified=random.random() > 0.3,
                confirms=random.randint(0, 20),
                denies=random.randint(0, 2),
                description="Seed data for area trend testing.",
                lat=base_lat + random.uniform(-0.01, 0.01),
                lng=base_lng + random.uniform(-0.01, 0.01),
                created_at=days_ago(age_days),
            ))

    for row in rows:
        db.add(models.Incident(reporter_id=user.id, **row))
    db.commit()
    print(f"Seeded {len(rows)} incidents.")


def seed_events():
    if db.query(models.Event).count() > 0:
        print("Events already seeded, skipping.")
        return

    events = [
        dict(name="Presidential Visit", icon="🎤", impact="elevated",
             description="Motorcade route through downtown -- expect rolling road closures and heavy security presence.",
             lat=40.7605, lng=-73.9800, starts_at=datetime.datetime(2026, 8, 24, 18, 0)),
        dict(name="City Marathon", icon="🏃", impact="high",
             description="Full closures along the riverfront route; detours posted for cross-town traffic.",
             lat=40.7460, lng=-73.9750, starts_at=datetime.datetime(2026, 9, 6, 11, 0)),
        dict(name="Downtown Parade", icon="🎉", impact="moderate",
             description="Street closures on Main Ave; moderate crowding expected near the plaza.",
             lat=40.7550, lng=-73.9900, starts_at=datetime.datetime(2026, 9, 14, 15, 0)),
        dict(name="Harbor Music Festival", icon="🎵", impact="moderate",
             description="Large crowds expected near the waterfront both evenings; limited parking.",
             lat=40.7010, lng=-74.0110, starts_at=datetime.datetime(2026, 9, 20, 21, 0)),
    ]
    for e in events:
        db.add(models.Event(**e))
    db.commit()
    print(f"Seeded {len(events)} events.")


if __name__ == "__main__":
    user = get_or_create_demo_user()
    print(f"Demo user ready: {user.email} / password123")
    seed_incidents(user)
    seed_events()
    db.close()
    print("Done.")
