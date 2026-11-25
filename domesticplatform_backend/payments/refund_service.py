"""
Central service for all payment release and refund operations.

All calls are idempotent: pass a stable `idempotency_key` (uuid.UUID) to
ensure the same operation cannot be applied twice.  In sandbox/mock mode the
B2C/reversal calls are simulated and the ledger row is marked SIMULATED.
"""

import uuid
import logging
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone as django_tz

from .models import Transaction, TransactionLedger
from .mpesa_service import mpesa_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _simulate_b2c(phone, amount, label):
    """Simulate a B2C payout in sandbox and log the result."""
    response = mpesa_service.b2c_payment(
        phone_number=phone,
        amount=float(amount),
        occasion=label,
    )
    return response


def _simulate_reversal(mpesa_reference, amount, label):
    """Simulate an M-Pesa reversal / STK refund in sandbox."""
    # In production this would call the M-Pesa Reversal API.
    # For sandbox we return a mock success and tag the ledger as SIMULATED.
    logger.info(f"[SANDBOX] Reversal of {mpesa_reference} for KES {amount}: {label}")
    return {'success': True, 'simulated': True}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@db_transaction.atomic
def release_to_student(task, actor=None, idempotency_key=None):
    """
    Release full escrow to the student.
    Returns (success: bool, message: str, ledger_entry).
    """
    idempotency_key = idempotency_key or uuid.uuid4()

    # Idempotency guard
    existing = TransactionLedger.objects.filter(
        task=task,
        transaction_type='RELEASE',
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return True, 'Already released (idempotent).', existing

    escrow = getattr(task, 'escrow_transaction', None)
    if not escrow or escrow.status != 'Held':
        return False, f'Escrow not in Held state (current: {escrow.status if escrow else "none"}).', None

    student = task.assigned_student
    if not student or not student.phone_number:
        return False, 'Student phone number unavailable.', None

    # Attempt B2C (simulated in sandbox)
    response = _simulate_b2c(
        student.phone_number,
        escrow.amount,
        f'Payment for Task {task.id}',
    )

    mpesa_ref = response.get('ConversationID', '') or response.get('CheckoutRequestID', '')
    sim_status = 'SIMULATED' if response.get('simulated') else 'COMPLETED'

    if response.get('success'):
        escrow.status = 'Released'
        escrow.save(update_fields=['status', 'updated_at'])

        entry, _ = TransactionLedger.record(
            task=task,
            transaction_type='RELEASE',
            amount=escrow.amount,
            actor=actor,
            mpesa_reference=mpesa_ref,
            notes=f'Released to {student.username}',
            idempotency_key=idempotency_key,
            status=sim_status,
        )

        from tasks.models import AuditLog
        AuditLog.log(
            task=task, actor=actor, action='payment_event',
            notes=f'RELEASE KES {escrow.amount} → {student.username} [{sim_status}]',
        )
        return True, 'Payment released to student.', entry
    else:
        return False, response.get('error', 'B2C failed.'), None


@db_transaction.atomic
def refund_to_household(task, actor=None, idempotency_key=None, partial_amount=None, notes=''):
    """
    Refund full or partial escrow to the household.
    `partial_amount`: Decimal — if None, full refund.
    Returns (success: bool, message: str, ledger_entry).
    """
    idempotency_key = idempotency_key or uuid.uuid4()
    tx_type = 'PARTIAL_REFUND' if partial_amount else 'REFUND'

    # Idempotency guard
    existing = TransactionLedger.objects.filter(
        task=task,
        transaction_type=tx_type,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return True, 'Already refunded (idempotent).', existing

    escrow = getattr(task, 'escrow_transaction', None)
    if not escrow or escrow.status not in ('Held',):
        return False, f'Escrow not in Held state (current: {escrow.status if escrow else "none"}).', None

    amount = Decimal(str(partial_amount)) if partial_amount else escrow.amount
    household = task.household_owner

    # Simulate reversal / M-Pesa refund
    mpesa_ref = escrow.mpesa_reference or ''
    response = _simulate_reversal(mpesa_ref, amount, f'Refund for Task {task.id}: {notes}')
    sim_status = 'SIMULATED' if response.get('simulated') else 'COMPLETED'

    if response.get('success'):
        escrow.status = 'Refunded' if not partial_amount else 'PartialRefund'
        escrow.save(update_fields=['status', 'updated_at'])

        entry, _ = TransactionLedger.record(
            task=task,
            transaction_type=tx_type,
            amount=amount,
            actor=actor,
            mpesa_reference=mpesa_ref,
            notes=notes or f'Refunded to {household.username}',
            idempotency_key=idempotency_key,
            status=sim_status,
        )

        from tasks.models import AuditLog
        AuditLog.log(
            task=task, actor=actor, action='payment_event',
            notes=f'{tx_type} KES {amount} → {household.username} [{sim_status}] {notes}',
        )
        return True, f'Refund of KES {amount} processed.', entry
    else:
        return False, response.get('error', 'Reversal failed.'), None
