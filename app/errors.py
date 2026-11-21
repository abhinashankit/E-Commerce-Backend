class DomainError(Exception):
    status_code = 400


class NotFound(DomainError):
    status_code = 404


class InsufficientStock(DomainError):
    status_code = 409


class PaymentGatewayError(DomainError):
    status_code = 502
