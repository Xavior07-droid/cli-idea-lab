"""
cli.py — Digital Legacy Vault, pure terminal edition

A menu-driven command-line interface that talks directly to the SAME
SQLite database as the Flask app (app.py), via the same models.py.
No Flask, no browser, no HTTP — just input()/print().

Run it:
    python cli.py

You can freely switch between this CLI and the web app (app.py) —
both read and write database/legacy_vault.db, so data added in one
shows up in the other.
"""
import os
import sys
from datetime import datetime, timedelta
from getpass import getpass

from flask import Flask

from models import (
    db,
    User,
    Asset,
    Nominee,
    WillInstruction,
    Document,
    DigitalAccount,
    TrustedContact,
    LifeVerification,
    Task,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Colour output (ANSI). On Windows, colorama translates ANSI codes for
# older terminals; modern Windows Terminal / PowerShell 7+ support ANSI
# natively, but calling colorama.init() is harmless either way.
# ---------------------------------------------------------------------------
try:
    import colorama
    colorama.init()
except ImportError:
    pass

GREEN = "\033[92m"
BRIGHT_GREEN = "\033[1;92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def green(text):
    return f"{GREEN}{text}{RESET}"


def bright_green(text):
    return f"{BRIGHT_GREEN}{text}{RESET}"


def yellow(text):
    return f"{YELLOW}{text}{RESET}"


# ---------------------------------------------------------------------------
# Bootstrap: we reuse Flask + SQLAlchemy just as a database engine here.
# There is no web server involved — app.run() is never called.
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    BASE_DIR, "database", "legacy_vault.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)
db.init_app(app)

with app.app_context():
    db.create_all()

# Current logged-in user, kept in memory for this terminal session only
current_user = None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
LOGO = r"""
  ____  _         __     __          _ _   
 |  _ \| |        \ \   / /_ _ _   _| | |_ 
 | | | | |         \ \ / / _` | | | | | __|
 | |_| | |____      \ V / (_| | |_| | | |_ 
 |____/|______|      \_/ \__,_|\__,_|_|\__|
       D I G I T A L   L E G A C Y   V A U L T"""


def pause():
    input("\nPress Enter to continue...")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header(title):
    clear()
    print(bright_green(LOGO))
    print(green("═" * 60))
    print(f"  {BOLD}{title.upper()}{RESET}")
    if current_user:
        print(f"  Logged in as: {CYAN}{current_user.full_name}{RESET} ({current_user.email})")
    print(green("═" * 60))
    print()



def prompt(label, required=True, default=None):
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            return default
        if value or not required:
            return value
        print("  This field is required.")


def prompt_float(label, default=0.0):
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number.")


def prompt_choice(label, choices):
    print(f"{label}:")
    for i, c in enumerate(choices, start=1):
        print(f"  {i}. {c}")
    while True:
        raw = input(f"Choose 1-{len(choices)}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print("  Invalid choice.")


def require_login():
    return current_user is not None


# ---------------------------------------------------------------------------
# Auth (Steps 1 & 2)
# ---------------------------------------------------------------------------
def register():
    header("Register")
    full_name = prompt("Full name")
    email = prompt("Email").lower()
    password = getpass("Password: ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("\nPasswords do not match.")
        pause()
        return

    if User.query.filter_by(email=email).first():
        print("\nAn account with this email already exists.")
        pause()
        return

    user = User(full_name=full_name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    print(f"\nAccount created for {full_name}. You can now log in.")
    pause()


def login():
    global current_user
    header("Login")
    email = prompt("Email").lower()
    password = getpass("Password: ")

    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        current_user = user
        print(f"\nWelcome back, {user.full_name}!")
    else:
        print("\nInvalid email or password.")
    pause()


def logout():
    global current_user
    current_user = None
    print("\nLogged out.")
    pause()


# ---------------------------------------------------------------------------
# Dashboard (Step 3)
# ---------------------------------------------------------------------------
def dashboard():
    header("Dashboard")
    u = current_user
    stats = [
        ("Assets", Asset.query.filter_by(user_id=u.id).count()),
        ("Nominees", Nominee.query.filter_by(user_id=u.id).count()),
        ("Documents", Document.query.filter_by(user_id=u.id).count()),
        ("Will Instructions", WillInstruction.query.filter_by(user_id=u.id).count()),
        ("Digital Accounts", DigitalAccount.query.filter_by(user_id=u.id).count()),
        ("Tasks", Task.query.filter_by(user_id=u.id).count()),
    ]
    for label, count in stats:
        print(f"  {label:<20}: {count}")

    verification = get_or_create_verification(u)
    status_line = "OK" if verification.status == "OK" else "VERIFICATION_REQUIRED"
    print(f"  {'Life Verification':<20}: {status_line}")
    pause()


# ---------------------------------------------------------------------------
# Asset Management (Step 4)
# ---------------------------------------------------------------------------
def assets_menu():
    while True:
        header("Assets")
        assets = Asset.query.filter_by(user_id=current_user.id).order_by(
            Asset.created_at.desc()
        ).all()
        if assets:
            for a in assets:
                print(f"  [{a.id}] {a.name}  ({a.category})  ~{a.approx_value}")
        else:
            print("  No assets yet.")

        print("\n1. Add asset  2. Edit asset  3. Delete asset  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            asset_add()
        elif choice == "2":
            asset_edit()
        elif choice == "3":
            asset_delete()
        elif choice == "0":
            return


def asset_add():
    header("Add Asset")
    name = prompt("Asset name")
    category = prompt("Category")
    provider = prompt("Provider", required=False)
    reference = prompt("Reference", required=False)
    approx_value = prompt_float("Approximate value")
    description = prompt("Description", required=False)

    asset = Asset(
        user_id=current_user.id,
        name=name,
        category=category,
        provider=provider,
        reference=reference,
        approx_value=approx_value,
        description=description,
    )
    db.session.add(asset)
    db.session.commit()
    print("\nAsset added.")
    pause()


def asset_edit():
    asset_id = input("Asset ID to edit: ").strip()
    asset = Asset.query.filter_by(id=asset_id, user_id=current_user.id).first()
    if not asset:
        print("\nAsset not found.")
        pause()
        return

    header(f"Edit Asset — {asset.name}")
    asset.name = prompt("Asset name", default=asset.name)
    asset.category = prompt("Category", default=asset.category)
    asset.provider = prompt("Provider", required=False, default=asset.provider or "")
    asset.reference = prompt("Reference", required=False, default=asset.reference or "")
    asset.approx_value = prompt_float("Approximate value", default=asset.approx_value)
    asset.description = prompt("Description", required=False, default=asset.description or "")

    db.session.commit()
    print("\nAsset updated.")
    pause()


def asset_delete():
    asset_id = input("Asset ID to delete: ").strip()
    asset = Asset.query.filter_by(id=asset_id, user_id=current_user.id).first()
    if not asset:
        print("\nAsset not found.")
        pause()
        return
    confirm = input(f"Type 'yes' to delete '{asset.name}': ").strip().lower()
    if confirm == "yes":
        db.session.delete(asset)
        db.session.commit()
        print("\nAsset deleted.")
    else:
        print("\nCancelled.")
    pause()


# ---------------------------------------------------------------------------
# Nominee Management (Step 5)
# ---------------------------------------------------------------------------
def nominees_menu():
    while True:
        header("Nominees")
        nominees = Nominee.query.filter_by(user_id=current_user.id).order_by(
            Nominee.created_at.desc()
        ).all()
        if nominees:
            for n in nominees:
                assigned = ", ".join(a.name for a in n.assets) or "None"
                print(f"  [{n.id}] {n.name} ({n.relationship_})  -> Assets: {assigned}")
        else:
            print("  No nominees yet.")

        print("\n1. Add nominee  2. Edit nominee  3. Delete nominee")
        print("4. Assign nominee to asset  5. Remove nominee from asset  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            nominee_add()
        elif choice == "2":
            nominee_edit()
        elif choice == "3":
            nominee_delete()
        elif choice == "4":
            assign_nominee()
        elif choice == "5":
            remove_nominee()
        elif choice == "0":
            return


def nominee_add():
    header("Add Nominee")
    name = prompt("Nominee name")
    relationship_ = prompt("Relationship (e.g. Mother, Brother)")
    email = prompt("Email", required=False)
    phone = prompt("Phone", required=False)

    nominee = Nominee(
        user_id=current_user.id,
        name=name,
        relationship_=relationship_,
        email=email,
        phone=phone,
    )
    db.session.add(nominee)
    db.session.commit()
    print("\nNominee added.")
    pause()


def nominee_edit():
    nominee_id = input("Nominee ID to edit: ").strip()
    nominee = Nominee.query.filter_by(id=nominee_id, user_id=current_user.id).first()
    if not nominee:
        print("\nNominee not found.")
        pause()
        return

    header(f"Edit Nominee — {nominee.name}")
    nominee.name = prompt("Nominee name", default=nominee.name)
    nominee.relationship_ = prompt("Relationship", default=nominee.relationship_)
    nominee.email = prompt("Email", required=False, default=nominee.email or "")
    nominee.phone = prompt("Phone", required=False, default=nominee.phone or "")

    db.session.commit()
    print("\nNominee updated.")
    pause()


def nominee_delete():
    nominee_id = input("Nominee ID to delete: ").strip()
    nominee = Nominee.query.filter_by(id=nominee_id, user_id=current_user.id).first()
    if not nominee:
        print("\nNominee not found.")
        pause()
        return
    confirm = input(f"Type 'yes' to delete '{nominee.name}': ").strip().lower()
    if confirm == "yes":
        db.session.delete(nominee)
        db.session.commit()
        print("\nNominee deleted.")
    else:
        print("\nCancelled.")
    pause()


def assign_nominee():
    header("Assign Nominee to Asset")
    asset_id = input("Asset ID: ").strip()
    asset = Asset.query.filter_by(id=asset_id, user_id=current_user.id).first()
    if not asset:
        print("\nAsset not found.")
        pause()
        return

    nominee_id = input("Nominee ID: ").strip()
    nominee = Nominee.query.filter_by(id=nominee_id, user_id=current_user.id).first()
    if not nominee:
        print("\nNominee not found.")
        pause()
        return

    if nominee in asset.nominees:
        print(f"\n{nominee.name} is already assigned to {asset.name}.")
    else:
        asset.nominees.append(nominee)
        db.session.commit()
        print(f"\n{nominee.name} assigned to {asset.name}.")
    pause()


def remove_nominee():
    header("Remove Nominee from Asset")
    asset_id = input("Asset ID: ").strip()
    asset = Asset.query.filter_by(id=asset_id, user_id=current_user.id).first()
    if not asset:
        print("\nAsset not found.")
        pause()
        return

    nominee_id = input("Nominee ID: ").strip()
    nominee = Nominee.query.filter_by(id=nominee_id, user_id=current_user.id).first()
    if not nominee or nominee not in asset.nominees:
        print("\nThat nominee is not assigned to this asset.")
        pause()
        return

    asset.nominees.remove(nominee)
    db.session.commit()
    print(f"\n{nominee.name} removed from {asset.name}.")
    pause()


# ---------------------------------------------------------------------------
# Will / Inheritance Instructions (Step 6)
# ---------------------------------------------------------------------------
def will_menu():
    while True:
        header("Will Instructions")
        instructions = WillInstruction.query.filter_by(
            user_id=current_user.id
        ).order_by(WillInstruction.created_at.desc()).all()
        if instructions:
            for i in instructions:
                asset_name = i.asset.name if i.asset else "(no asset)"
                print(f"  [{i.id}] {asset_name} -> {i.beneficiary_name}: {i.instruction_text}")
        else:
            print("  No will instructions yet.")

        print("\n1. Add instruction  2. Edit instruction  3. Delete instruction  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            will_add()
        elif choice == "2":
            will_edit()
        elif choice == "3":
            will_delete()
        elif choice == "0":
            return


def _pick_asset_id_optional():
    assets = Asset.query.filter_by(user_id=current_user.id).all()
    if not assets:
        print("  (No assets yet — instruction will not be tied to a specific asset.)")
        return None
    print("  Assets:", ", ".join(f"[{a.id}] {a.name}" for a in assets))
    raw = input("  Asset ID (leave blank for none): ").strip()
    return int(raw) if raw else None


def will_add():
    header("Add Will Instruction")
    asset_id = _pick_asset_id_optional()
    beneficiary_name = prompt("Beneficiary name")
    instruction_text = prompt("Instruction (e.g. 'Transfer property to mother')")

    instruction = WillInstruction(
        user_id=current_user.id,
        asset_id=asset_id,
        beneficiary_name=beneficiary_name,
        instruction_text=instruction_text,
    )
    db.session.add(instruction)
    db.session.commit()
    print("\nWill instruction added.")
    pause()


def will_edit():
    instruction_id = input("Instruction ID to edit: ").strip()
    instruction = WillInstruction.query.filter_by(
        id=instruction_id, user_id=current_user.id
    ).first()
    if not instruction:
        print("\nInstruction not found.")
        pause()
        return

    header("Edit Will Instruction")
    asset_id = _pick_asset_id_optional()
    instruction.asset_id = asset_id
    instruction.beneficiary_name = prompt("Beneficiary name", default=instruction.beneficiary_name)
    instruction.instruction_text = prompt("Instruction", default=instruction.instruction_text)

    db.session.commit()
    print("\nWill instruction updated.")
    pause()


def will_delete():
    instruction_id = input("Instruction ID to delete: ").strip()
    instruction = WillInstruction.query.filter_by(
        id=instruction_id, user_id=current_user.id
    ).first()
    if not instruction:
        print("\nInstruction not found.")
        pause()
        return
    confirm = input("Type 'yes' to delete this instruction: ").strip().lower()
    if confirm == "yes":
        db.session.delete(instruction)
        db.session.commit()
        print("\nInstruction deleted.")
    else:
        print("\nCancelled.")
    pause()


# ---------------------------------------------------------------------------
# Will Checker (Step 7) — same rules as the web app, no AI
# ---------------------------------------------------------------------------
def will_checker():
    header("Will Checker")
    u = current_user
    assets = Asset.query.filter_by(user_id=u.id).all()
    instructions = WillInstruction.query.filter_by(user_id=u.id).all()

    results = []

    for asset in assets:
        has_instruction = any(i.asset_id == asset.id for i in instructions)
        results.append((
            "PASS" if has_instruction else "WARNING",
            f'"{asset.name}" ' + ("is covered by a will instruction."
                                   if has_instruction else "has no will instruction linked to it."),
        ))

    for instruction in instructions:
        broken = instruction.asset_id is not None and instruction.asset is None
        results.append((
            "WARNING" if broken else "PASS",
            f'Instruction for "{instruction.beneficiary_name}" '
            + ("refers to an asset that no longer exists."
               if broken else
               (f'refers to "{instruction.asset.name}".' if instruction.asset
                else "is not tied to a specific asset.")),
        ))

    for asset in assets:
        results.append((
            "PASS" if asset.nominees else "WARNING",
            f'"{asset.name}" ' + ("has at least one nominee assigned."
                                   if asset.nominees else "has no nominee assigned."),
        ))

    for instruction in instructions:
        has_ben = bool(instruction.beneficiary_name and instruction.beneficiary_name.strip())
        results.append((
            "PASS" if has_ben else "WARNING",
            (f'Instruction is assigned to beneficiary "{instruction.beneficiary_name}".'
             if has_ben else "Instruction has no beneficiary specified."),
        ))

    if not results:
        print("  Nothing to check yet — add some assets and will instructions first.")
    else:
        for status, detail in results:
            print(f"  [{status:<7}] {detail}")
        pass_count = sum(1 for s, _ in results if s == "PASS")
        warn_count = sum(1 for s, _ in results if s == "WARNING")
        print(f"\n  Total: {pass_count} PASS, {warn_count} WARNING")
    pause()


# ---------------------------------------------------------------------------
# Document Management (Step 8)
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def documents_menu():
    while True:
        header("Documents")
        documents = Document.query.filter_by(user_id=current_user.id).order_by(
            Document.uploaded_at.desc()
        ).all()
        if documents:
            for d in documents:
                size_kb = round((d.file_size or 0) / 1024, 1)
                print(f"  [{d.id}] {d.original_filename}  ({d.category})  {size_kb} KB")
        else:
            print("  No documents yet.")

        print("\n1. Add document (by file path)  2. Delete document  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            document_add()
        elif choice == "2":
            document_delete()
        elif choice == "0":
            return


def document_add():
    header("Add Document")
    print("  Enter the full path to a file already on this computer.")
    print("  Allowed types: PDF, JPG, JPEG, PNG")
    filepath = prompt("File path")

    if not os.path.isfile(filepath):
        print("\nFile not found at that path.")
        pause()
        return

    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
    if ext not in ALLOWED_EXTENSIONS:
        print("\nOnly PDF, JPG, JPEG and PNG files are allowed.")
        pause()
        return

    category = prompt("Category", required=False, default="Other")
    description = prompt("Description", required=False)

    import shutil
    import uuid as uuid_module

    upload_dir = os.path.join(BASE_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    original_filename = os.path.basename(filepath)
    stored_filename = f"{uuid_module.uuid4().hex}.{ext}"
    dest = os.path.join(upload_dir, stored_filename)
    shutil.copyfile(filepath, dest)
    file_size = os.path.getsize(dest)

    document = Document(
        user_id=current_user.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        category=category or "Other",
        description=description,
        file_size=file_size,
    )
    db.session.add(document)
    db.session.commit()
    print(f"\nDocument '{original_filename}' added.")
    pause()


def document_delete():
    doc_id = input("Document ID to delete: ").strip()
    doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first()
    if not doc:
        print("\nDocument not found.")
        pause()
        return
    confirm = input(f"Type 'yes' to delete '{doc.original_filename}': ").strip().lower()
    if confirm == "yes":
        filepath = os.path.join(BASE_DIR, "uploads", doc.stored_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        db.session.delete(doc)
        db.session.commit()
        print("\nDocument deleted.")
    else:
        print("\nCancelled.")
    pause()


# ---------------------------------------------------------------------------
# Digital Legacy (Step 9)
# ---------------------------------------------------------------------------
DIGITAL_ACCOUNT_ACTIONS = ["Preserve", "Memorialize", "Transfer", "Delete"]


def digital_legacy_menu():
    while True:
        header("Digital Legacy")
        accounts = DigitalAccount.query.filter_by(user_id=current_user.id).order_by(
            DigitalAccount.created_at.desc()
        ).all()
        if accounts:
            for a in accounts:
                print(f"  [{a.id}] {a.service} ({a.account_identifier}) -> {a.action}, beneficiary: {a.beneficiary or '-'}")
        else:
            print("  No digital accounts yet.")

        print("\n1. Add account  2. Edit account  3. Delete account  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            digital_account_add()
        elif choice == "2":
            digital_account_edit()
        elif choice == "3":
            digital_account_delete()
        elif choice == "0":
            return


def digital_account_add():
    header("Add Digital Account")
    service = prompt("Service (e.g. Google, Facebook)")
    account_identifier = prompt("Account identifier (e.g. email/username)")
    action = prompt_choice("Action", DIGITAL_ACCOUNT_ACTIONS)
    beneficiary = prompt("Beneficiary", required=False)
    instructions = prompt("Instructions", required=False)

    account = DigitalAccount(
        user_id=current_user.id,
        service=service,
        account_identifier=account_identifier,
        action=action,
        beneficiary=beneficiary,
        instructions=instructions,
    )
    db.session.add(account)
    db.session.commit()
    print("\nDigital account added.")
    pause()


def digital_account_edit():
    account_id = input("Account ID to edit: ").strip()
    account = DigitalAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
    if not account:
        print("\nAccount not found.")
        pause()
        return

    header(f"Edit Digital Account — {account.service}")
    account.service = prompt("Service", default=account.service)
    account.account_identifier = prompt("Account identifier", default=account.account_identifier)
    account.action = prompt_choice("Action", DIGITAL_ACCOUNT_ACTIONS)
    account.beneficiary = prompt("Beneficiary", required=False, default=account.beneficiary or "")
    account.instructions = prompt("Instructions", required=False, default=account.instructions or "")

    db.session.commit()
    print("\nDigital account updated.")
    pause()


def digital_account_delete():
    account_id = input("Account ID to delete: ").strip()
    account = DigitalAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
    if not account:
        print("\nAccount not found.")
        pause()
        return
    confirm = input(f"Type 'yes' to delete '{account.service}': ").strip().lower()
    if confirm == "yes":
        db.session.delete(account)
        db.session.commit()
        print("\nDigital account deleted.")
    else:
        print("\nCancelled.")
    pause()


# ---------------------------------------------------------------------------
# Trusted Contact (Step 10)
# ---------------------------------------------------------------------------
def trusted_contacts_menu():
    while True:
        header("Trusted Contacts")
        contacts = TrustedContact.query.filter_by(user_id=current_user.id).order_by(
            TrustedContact.created_at.desc()
        ).all()
        if contacts:
            for c in contacts:
                print(f"  [{c.id}] {c.name} ({c.relationship_})  {c.email or '-'}  {c.phone or '-'}")
        else:
            print("  No trusted contacts yet.")

        print("\n1. Add contact  2. Edit contact  3. Delete contact  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            trusted_contact_add()
        elif choice == "2":
            trusted_contact_edit()
        elif choice == "3":
            trusted_contact_delete()
        elif choice == "0":
            return


def trusted_contact_add():
    header("Add Trusted Contact")
    name = prompt("Name")
    relationship_ = prompt("Relationship")
    email = prompt("Email", required=False)
    phone = prompt("Phone", required=False)

    contact = TrustedContact(
        user_id=current_user.id,
        name=name,
        relationship_=relationship_,
        email=email,
        phone=phone,
    )
    db.session.add(contact)
    db.session.commit()
    print("\nTrusted contact added.")
    pause()


def trusted_contact_edit():
    contact_id = input("Contact ID to edit: ").strip()
    contact = TrustedContact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    if not contact:
        print("\nContact not found.")
        pause()
        return

    header(f"Edit Trusted Contact — {contact.name}")
    contact.name = prompt("Name", default=contact.name)
    contact.relationship_ = prompt("Relationship", default=contact.relationship_)
    contact.email = prompt("Email", required=False, default=contact.email or "")
    contact.phone = prompt("Phone", required=False, default=contact.phone or "")

    db.session.commit()
    print("\nTrusted contact updated.")
    pause()


def trusted_contact_delete():
    contact_id = input("Contact ID to delete: ").strip()
    contact = TrustedContact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    if not contact:
        print("\nContact not found.")
        pause()
        return
    confirm = input(f"Type 'yes' to delete '{contact.name}': ").strip().lower()
    if confirm == "yes":
        db.session.delete(contact)
        db.session.commit()
        print("\nTrusted contact deleted.")
    else:
        print("\nCancelled.")
    pause()


# ---------------------------------------------------------------------------
# Life Verification (Step 11) — SIMULATION ONLY
# ---------------------------------------------------------------------------
def get_or_create_verification(user):
    record = LifeVerification.query.filter_by(user_id=user.id).first()
    if not record:
        now = datetime.utcnow()
        record = LifeVerification(
            user_id=user.id,
            last_verified_at=now,
            next_verification_due=now + timedelta(days=30),
            status="OK",
            verification_interval_days=30,
        )
        db.session.add(record)
        db.session.commit()
    return record


def life_verification_menu():
    header("Life Verification")
    record = get_or_create_verification(current_user)

    if record.next_verification_due < datetime.utcnow() and record.status == "OK":
        record.status = "VERIFICATION_REQUIRED"
        db.session.commit()

    print(f"  Last Verification     : {record.last_verified_at.strftime('%d %b %Y, %I:%M %p')}")
    print(f"  Next Verification Due : {record.next_verification_due.strftime('%d %b %Y, %I:%M %p')}")
    print(f"  Status                : {record.status}")
    print(f"  Check-in Interval     : every {record.verification_interval_days} days")

    if record.status != "OK":
        print("\n  WARNING: Verification window missed.")
        print("  Nothing has been released or changed — this is a demo only.")

    print("\n1. Confirm I Am Alive  2. Simulate Missed Verification (demo)  0. Back")
    choice = input("> ").strip()

    if choice == "1":
        now = datetime.utcnow()
        record.last_verified_at = now
        record.next_verification_due = now + timedelta(days=record.verification_interval_days)
        record.status = "OK"
        db.session.commit()
        print("\nLife status confirmed. Next verification date reset.")
        pause()
    elif choice == "2":
        record.next_verification_due = datetime.utcnow() - timedelta(days=1)
        record.status = "VERIFICATION_REQUIRED"
        db.session.commit()
        print("\nSimulated a missed verification. Nothing was released — demo only.")
        pause()


# ---------------------------------------------------------------------------
# Inheritance Tasks (Step 12)
# ---------------------------------------------------------------------------
TASK_STATUSES = ["Pending", "In Progress", "Completed"]


def tasks_menu():
    while True:
        header("Inheritance Tasks")
        tasks = Task.query.filter_by(user_id=current_user.id).order_by(
            Task.created_at.desc()
        ).all()
        if tasks:
            for t in tasks:
                print(f"  [{t.id}] {t.title}  -  {t.status}")
        else:
            print("  No tasks yet.")

        print("\n1. Add task  2. Edit task  3. Change status  4. Delete task  0. Back")
        choice = input("> ").strip()

        if choice == "1":
            task_add()
        elif choice == "2":
            task_edit()
        elif choice == "3":
            task_change_status()
        elif choice == "4":
            task_delete()
        elif choice == "0":
            return


def task_add():
    header("Add Task")
    title = prompt("Task title (e.g. 'Contact Bank')")
    description = prompt("Description", required=False)
    status = prompt_choice("Status", TASK_STATUSES)

    task = Task(
        user_id=current_user.id,
        title=title,
        description=description,
        status=status,
    )
    db.session.add(task)
    db.session.commit()
    print("\nTask added.")
    pause()


def task_edit():
    task_id = input("Task ID to edit: ").strip()
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        print("\nTask not found.")
        pause()
        return

    header(f"Edit Task — {task.title}")
    task.title = prompt("Task title", default=task.title)
    task.description = prompt("Description", required=False, default=task.description or "")
    task.status = prompt_choice("Status", TASK_STATUSES)

    db.session.commit()
    print("\nTask updated.")
    pause()


def task_change_status():
    task_id = input("Task ID: ").strip()
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        print("\nTask not found.")
        pause()
        return
    task.status = prompt_choice("New status", TASK_STATUSES)
    db.session.commit()
    print(f"\nTask '{task.title}' marked as {task.status}.")
    pause()


def task_delete():
    task_id = input("Task ID to delete: ").strip()
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        print("\nTask not found.")
        pause()
        return
    confirm = input(f"Type 'yes' to delete '{task.title}': ").strip().lower()
    if confirm == "yes":
        db.session.delete(task)
        db.session.commit()
        print("\nTask deleted.")
    else:
        print("\nCancelled.")
    pause()


# ---------------------------------------------------------------------------
# Main menu / entry point
# ---------------------------------------------------------------------------
def logged_out_menu():
    header("Welcome")
    print("1. Register")
    print("2. Login")
    print("0. Exit")
    return input("> ").strip()


def logged_in_menu():
    header("Main Menu")
    print("1. Dashboard")
    print("2. Assets")
    print("3. Nominees")
    print("4. Will Instructions")
    print("5. Will Checker")
    print("6. Documents")
    print("7. Digital Legacy")
    print("8. Trusted Contacts")
    print("9. Life Verification")
    print("10. Inheritance Tasks")
    print("0. Logout")
    return input("> ").strip()


def main():
    with app.app_context():
        while True:
            if not require_login():
                choice = logged_out_menu()
                if choice == "1":
                    register()
                elif choice == "2":
                    login()
                elif choice == "0":
                    print("\nGoodbye.")
                    sys.exit(0)
            else:
                choice = logged_in_menu()
                if choice == "1":
                    dashboard()
                elif choice == "2":
                    assets_menu()
                elif choice == "3":
                    nominees_menu()
                elif choice == "4":
                    will_menu()
                elif choice == "5":
                    will_checker()
                elif choice == "6":
                    documents_menu()
                elif choice == "7":
                    digital_legacy_menu()
                elif choice == "8":
                    trusted_contacts_menu()
                elif choice == "9":
                    life_verification_menu()
                elif choice == "10":
                    tasks_menu()
                elif choice == "0":
                    logout()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nGoodbye.")
        sys.exit(0)
