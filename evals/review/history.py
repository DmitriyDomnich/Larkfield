from app.claims.status import ClaimStatus
from app.extraction.models import ExpenseCategory
from app.review.claim_data import ClaimUnderReview
from app.review.claims_history import PossibleClaimDuplicate, TrainingClaim


class RunHistory:
    def __init__(self) -> None:
        self._claims: list[ClaimUnderReview] = []

    def add(self, claim: ClaimUnderReview) -> None:
        self._claims.append(claim)

    def _submitted_before(self, claim: ClaimUnderReview) -> list[ClaimUnderReview]:
        earlier = [
            other
            for other in self._claims
            if (other.submitted_at, other.claim_id) < (claim.submitted_at, claim.claim_id)
        ]
        return sorted(earlier, key=lambda other: other.submitted_at)

    async def find_possible_duplicates(
        self, claim: ClaimUnderReview
    ) -> list[PossibleClaimDuplicate]:
        expense = claim.expense
        found = []
        for other in self._submitted_before(claim):
            same_file = claim.document_sha256 is not None and (
                other.document_sha256 == claim.document_sha256
            )
            same_expense = (
                other.expense.document_date == expense.document_date
                and other.expense.total == expense.total
                and other.expense.currency == expense.currency
            )
            if same_expense or same_file:
                found.append(
                    PossibleClaimDuplicate(
                        claim_id=other.claim_id,
                        vendor_name=other.expense.vendor_name,
                        vendor_tax_id=other.expense.vendor_tax_id,
                        document_number=other.expense.document_number,
                        document_date=other.expense.document_date,
                        total=other.expense.total,
                        currency=other.expense.currency,
                        status=ClaimStatus.IN_REVIEW,
                        same_employee=other.employee_sub == claim.employee_sub,
                        same_file=same_file,
                    )
                )
        return found

    async def list_training_claims(self, claim: ClaimUnderReview) -> list[TrainingClaim]:
        year = claim.expense.document_date.year
        training = [
            other
            for other in self._submitted_before(claim)
            if other.employee_sub == claim.employee_sub
            and other.expense.category is ExpenseCategory.TRAINING
            and other.expense.document_date.year == year
        ]
        return [
            TrainingClaim(
                claim_id=other.claim_id,
                document_date=other.expense.document_date,
                total=other.expense.total,
                currency=other.expense.currency,
                status=ClaimStatus.IN_REVIEW,
            )
            for other in sorted(training, key=lambda other: other.expense.document_date)
        ]
