"""Calendar dimension generator."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.seeder.config import HolidayConfig


# US Federal Holidays (fixed dates or patterns)
DEFAULT_US_HOLIDAYS = {
    # Fixed date holidays
    (1, 1): "New Year's Day",
    (7, 4): "Independence Day",
    (11, 11): "Veterans Day",
    (12, 25): "Christmas Day",
}


def _get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Get the nth occurrence of a weekday in a month.

    Args:
        year: Year.
        month: Month (1-12).
        weekday: Day of week (0=Monday, 6=Sunday).
        n: Which occurrence (1=first, 2=second, etc.).

    Returns:
        Date of the nth weekday in the month.
    """
    first_day = date(year, month, 1)
    # Find first occurrence of weekday
    days_until = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=days_until)
    # Add weeks for nth occurrence
    return first_occurrence + timedelta(weeks=n - 1)


def _get_last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Get the last occurrence of a weekday in a month.

    Args:
        year: Year.
        month: Month (1-12).
        weekday: Day of week (0=Monday, 6=Sunday).

    Returns:
        Date of the last weekday in the month.
    """
    # Start from last day of month
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Find last occurrence of weekday
    days_back = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_back)


def get_us_holidays_for_year(year: int) -> dict[date, str]:
    """Get US federal holidays for a given year.

    Args:
        year: Year to get holidays for.

    Returns:
        Dictionary mapping date to holiday name.
    """
    holidays: dict[date, str] = {}

    # Fixed date holidays
    for (month, day), name in DEFAULT_US_HOLIDAYS.items():
        holidays[date(year, month, day)] = name

    # Variable holidays (based on weekday rules)
    # MLK Day: 3rd Monday of January
    holidays[_get_nth_weekday_of_month(year, 1, 0, 3)] = "Martin Luther King Jr. Day"

    # Presidents Day: 3rd Monday of February
    holidays[_get_nth_weekday_of_month(year, 2, 0, 3)] = "Presidents Day"

    # Memorial Day: Last Monday of May
    holidays[_get_last_weekday_of_month(year, 5, 0)] = "Memorial Day"

    # Labor Day: 1st Monday of September
    holidays[_get_nth_weekday_of_month(year, 9, 0, 1)] = "Labor Day"

    # Columbus Day: 2nd Monday of October
    holidays[_get_nth_weekday_of_month(year, 10, 0, 2)] = "Columbus Day"

    # Thanksgiving: 4th Thursday of November
    holidays[_get_nth_weekday_of_month(year, 11, 3, 4)] = "Thanksgiving"

    return holidays


class CalendarGenerator:
    """Generator for calendar dimension data."""

    def __init__(
        self,
        start_date: date,
        end_date: date,
        custom_holidays: list[HolidayConfig] | None = None,
    ) -> None:
        """Initialize the calendar generator.

        Args:
            start_date: Start of date range.
            end_date: End of date range (inclusive).
            custom_holidays: Optional list of custom holiday configurations.
        """
        self.start_date = start_date
        self.end_date = end_date
        self.custom_holidays = custom_holidays or []

    def _build_holiday_map(self) -> dict[date, str]:
        """Build combined holiday map from US holidays and custom holidays.

        Returns:
            Dictionary mapping date to holiday name.
        """
        holidays: dict[date, str] = {}

        # Get years in range
        years = set()
        current = self.start_date
        while current <= self.end_date:
            years.add(current.year)
            current += timedelta(days=365)  # Approximate, we'll dedupe
        years.add(self.end_date.year)

        # Add US holidays for each year
        for year in years:
            holidays.update(get_us_holidays_for_year(year))

        # Add custom holidays (override US holidays if same date)
        for holiday in self.custom_holidays:
            holidays[holiday.date] = holiday.name

        return holidays

    def generate(self) -> list[dict[str, date | int | bool | str | None]]:
        """Generate calendar dimension records.

        Returns:
            List of calendar dictionaries ready for database insertion.
        """
        holidays = self._build_holiday_map()
        calendar_records: list[dict[str, date | int | bool | str | None]] = []

        current = self.start_date
        while current <= self.end_date:
            holiday_name = holidays.get(current)
            record: dict[str, date | int | bool | str | None] = {
                "date": current,
                "day_of_week": current.weekday(),  # 0=Monday, 6=Sunday
                "month": current.month,
                "quarter": (current.month - 1) // 3 + 1,
                "year": current.year,
                "is_holiday": holiday_name is not None,
                "holiday_name": holiday_name,
            }
            calendar_records.append(record)
            current += timedelta(days=1)

        return calendar_records
