"""
Jalali (Shamsi) date helper.
Used ONLY for display/input conversion on forms — the database
keeps storing standard Gregorian dates (DateField is unchanged).
"""
import jdatetime


def to_jalali_str(gregorian_date):
    """Convert a Python date to a Jalali string 'YYYY/MM/DD'."""
    if gregorian_date is None:
        return ''
    j = jdatetime.date.fromgregorian(date=gregorian_date)
    return j.strftime('%Y/%m/%d')


def jalali_str_to_gregorian(jalali_str):
    """
    Convert a Jalali string 'YYYY/MM/DD' (or with '-') typed by the user
    into a Python date object for saving to the DB.
    Raises ValueError with a Farsi message if the format is invalid.
    """
    if not jalali_str:
        raise ValueError('تاریخ را وارد کنید.')

    cleaned = jalali_str.strip().replace('-', '/')
    parts = cleaned.split('/')
    if len(parts) != 3:
        raise ValueError('فرمت تاریخ نادرست است. مثال صحیح: 1405/04/11')

    try:
        year, month, day = (int(p) for p in parts)
        jd = jdatetime.date(year, month, day)
        return jd.togregorian()
    except (ValueError, TypeError):
        raise ValueError('تاریخ وارد شده معتبر نیست. مثال صحیح: 1405/04/11')


def jalali_month_range_str(year, month):
    """
    Return (first_day, last_day) of a given Jalali year/month as
    'YYYY/MM/DD' strings — e.g. (1405/03/01, 1405/03/31).

    Used to build date_from/date_to query params (already understood by
    expense_list's existing Jalali filter logic) for a specific Jalali
    month, without needing any Gregorian year/month filtering anywhere.
    """
    first_day = f'{year}/{month:02d}/01'
    last_day_num = 31
    while last_day_num > 1:
        try:
            jdatetime.date(year, month, last_day_num)
            break
        except ValueError:
            last_day_num -= 1
    last_day = f'{year}/{month:02d}/{last_day_num:02d}'
    return first_day, last_day