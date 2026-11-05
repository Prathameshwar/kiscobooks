"""A frozen amount written out in English words, for the "amount in words" line of a print.

Display only: the amount is an authoritative, already-calculated figure and nothing here rounds
money for any other purpose. Grouping follows the company's digit grouping (Indian: thousand,
lakh, crore; Western: thousand, million, billion). The words are English whatever language a
template's own text is in (designer plan D5: one language per template, typed by its author).
"""

from decimal import Decimal

from billing_platform.display import DisplayConfiguration

ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen "
    "Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()
#: Whole and fractional unit names for the currencies whose minor unit is a hundredth.
CURRENCIES = {
    "INR": ("Rupees", "Paise"),
    "USD": ("Dollars", "Cents"),
    "EUR": ("Euros", "Cents"),
    "GBP": ("Pounds", "Pence"),
    "AED": ("Dirhams", "Fils"),
    "SGD": ("Dollars", "Cents"),
    "AUD": ("Dollars", "Cents"),
    "CAD": ("Dollars", "Cents"),
}
INDIAN = ((10**7, "Crore"), (10**5, "Lakh"), (10**3, "Thousand"))
WESTERN = ((10**12, "Trillion"), (10**9, "Billion"), (10**6, "Million"), (10**3, "Thousand"))


def below_thousand(value: int) -> str:
    words = []
    if value >= 100:
        words.append(f"{ONES[value // 100]} Hundred")
        value %= 100
    if value >= 20:
        words.append(TENS[value // 10] + (f"-{ONES[value % 10]}" if value % 10 else ""))
    elif value or not words:
        words.append(ONES[value])
    return " ".join(words)


def whole(value: int, grouping: str) -> str:
    """``value`` (>= 0) in words; Indian grouping repeats crores above 99 crore."""
    if value < 1000:
        return below_thousand(value)
    scales = INDIAN if grouping == "indian" else WESTERN
    words = []
    for size, name in scales:
        if value >= size:
            count, value = divmod(value, size)
            words.append(f"{whole(count, grouping)} {name}")
    if value:
        words.append(below_thousand(value))
    return " ".join(words)


def amount_in_words(amount: Decimal | str, currency: str, config: DisplayConfiguration) -> str:
    """For example ``Rupees One Lakh Twenty Thousand and Fifty Paise Only``."""
    value = Decimal(amount)
    if not value.is_finite() or abs(value) >= Decimal(10) ** 18:
        raise ValueError("amount in words is outside its bound")
    places = config.amount_precision
    # The printed total's own rounding, so the words can never read differently.
    value = value.quantize(
        Decimal(1).scaleb(-places), rounding=config.rounding_mode.decimal_rounding
    )
    negative = value < 0
    integer, fraction = divmod(abs(value), 1)
    major, minor = CURRENCIES.get(currency, (currency, ""))
    text = f"{major} {whole(int(integer), config.digit_grouping)}"
    hundredths = int(fraction * 100)
    if fraction and places == 2 and minor:
        text += f" and {whole(hundredths, config.digit_grouping)} {minor}"
    elif fraction:
        digits = format(fraction, "f").partition(".")[2].rstrip("0")
        text += " Point " + " ".join(ONES[int(digit)] for digit in digits)
    return ("Minus " if negative else "") + text + " Only"
