"""Recompute monetary comparisons from exact script quotations, not model arithmetic."""
import re
from decimal import Decimal, InvalidOperation

SMALL = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety'.split(), list(range(21)) + list(range(30, 100, 10))))
SCALE = {'hundred': 100, 'thousand': 1000, 'million': 10**6, 'billion': 10**9, 'trillion': 10**12}
NUM = r'(?:\d[\d,.]*|a|an|' + '|'.join(SMALL) + '|' + '|'.join(SCALE) + r')'
AMOUNT = re.compile(r'(?<!\w)\$?(' + NUM + r'(?:[ -]+' + NUM + r')*)(?!\w)', re.I)
RATIO = re.compile(r'(' + NUM + r'(?:[ -]+' + NUM + r')*)[ -]+times\b', re.I)


def number(phrase):
    tokens = phrase.lower().replace(',', '').replace('-', ' ').split()
    total = Decimal(0)
    group = Decimal(0)
    for token in tokens:
        if token in ('a', 'an'):
            group += 1
        elif token in SMALL:
            group += SMALL[token]
        elif token == 'hundred':
            group = (group or Decimal(1)) * 100
        elif token in SCALE:
            total += (group or Decimal(1)) * SCALE[token]
            group = Decimal(0)
        else:
            group += Decimal(token)
    return total + group


def amount(quote):
    # Require a monetary scale or dollar sign, avoiding incidental dates/counts.
    if not re.search(r'\$|\b(?:dollars?|million|billion|trillion)\b', quote, re.I):
        raise ValueError('not a monetary amount')
    matches = [m for m in AMOUNT.finditer(quote) if m.group(1).lower() not in ('a', 'an')]
    if len(matches) != 1:
        raise ValueError('ambiguous amount')
    return number(matches[0].group(1))


def check_calculations(script, rows):
    errors, unresolved, covered = [], [], set()
    if not isinstance(rows, list):
        return [], ['Fact audit omitted calculations array']
    for row in rows:
        try:
            exact = row['exact_line']
            if exact not in script.splitlines():
                raise ValueError('calculation line absent')
            left, right = row['left_quote'], row['right_quote']
            if not left or not right or left not in script or right not in script:
                raise ValueError('operands not quoted from script')
            numerator, denominator = amount(left), amount(right)
            operation = row['operation']
            if operation == 'ratio':
                quote = row['ratio_quote']
                match = RATIO.fullmatch(quote)
                if quote not in exact or not match or not denominator:
                    raise ValueError('invalid ratio quotation')
                actual = numerator / denominator
                claimed = number(match.group(1))
                wrong = abs(claimed - actual) > max(abs(actual) * Decimal('.05'), Decimal('.01'))
                reason = f'Arithmetic: {numerator} / {denominator} = {actual}, not {claimed}'
            elif operation == 'greater_than':
                if not re.search(r'\bmore\b.*\bthan\b', exact, re.I):
                    raise ValueError('missing comparative claim')
                wrong = numerator <= denominator
                reason = f'Arithmetic: {numerator} is not greater than {denominator}'
            else:
                raise ValueError('unknown operation')
            covered.add(exact)
            if wrong:
                replacement = row.get('replacement_line', '')
                if (replacement == exact or '\n' in replacement or
                    not replacement.startswith(exact.split(':', 1)[0] + ':')):
                    replacement = ''
                errors.append({'claim_type': 'arithmetic', 'exact_line': exact,
                               'replacement_line': replacement, 'reason': reason})
        except (KeyError, TypeError, ValueError, InvalidOperation, ZeroDivisionError):
            unresolved.append('Invalid or ungrounded calculation record')
    for line in script.splitlines():
        # Catch omitted finance multiples even when the provider says "pass".
        if (re.match(r'^(ALEX|JAMIE|RUFUS):', line) and
            (re.search(r'\btimes\s+(?:annual(?:ized)?\s+)?(?:revenue|sales|earnings)\b', line, re.I)
             or re.search(r'rais\w* more money than.*acquisition', line, re.I)) and line not in covered):
            unresolved.append('Numerical comparison not audited: ' + line)
    return errors, unresolved
