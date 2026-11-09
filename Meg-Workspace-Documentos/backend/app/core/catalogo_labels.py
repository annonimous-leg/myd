"""Product labels are separate from immutable source identities and evidence."""
from datetime import date

_MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
           'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def market_research_label(effective_date: str | date | None) -> str:
    try:
        value = date.fromisoformat(effective_date) if isinstance(effective_date, str) else effective_date
        if not isinstance(value, date):
            raise ValueError('Missing source date')
    except ValueError:
        return 'Investigación de mercado Megalodon · fecha por verificar'
    return f'Investigación de mercado Megalodon · {_MONTHS[value.month - 1]} {value.year}'
