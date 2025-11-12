#!/usr/bin/env python3
"""
Saurellius Tax Calculator - All 50 States + Local Taxes
Complete federal, state, local, SDI, and FICA calculations
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

# ============================================================================
# FEDERAL TAX CONSTANTS (2025)
# ============================================================================

SOCIAL_SECURITY_RATE = Decimal('0.062')
SOCIAL_SECURITY_WAGE_BASE = Decimal('168600')  # 2025
MEDICARE_RATE = Decimal('0.0145')
ADDITIONAL_MEDICARE_RATE = Decimal('0.009')
ADDITIONAL_MEDICARE_THRESHOLD_SINGLE = Decimal('200000')
ADDITIONAL_MEDICARE_THRESHOLD_MARRIED = Decimal('250000')

# Federal Income Tax Brackets 2025 (Annualized)
FEDERAL_TAX_BRACKETS_2025 = {
    'single': [
        (Decimal('11600'), Decimal('0.10')),
        (Decimal('47150'), Decimal('0.12')),
        (Decimal('100525'), Decimal('0.22')),
        (Decimal('191950'), Decimal('0.24')),
        (Decimal('243725'), Decimal('0.32')),
        (Decimal('609350'), Decimal('0.35')),
        (float('inf'), Decimal('0.37'))
    ],
    'married': [
        (Decimal('23200'), Decimal('0.10')),
        (Decimal('94300'), Decimal('0.12')),
        (Decimal('201050'), Decimal('0.22')),
        (Decimal('383900'), Decimal('0.24')),
        (Decimal('487450'), Decimal('0.32')),
        (Decimal('731200'), Decimal('0.35')),
        (float('inf'), Decimal('0.37'))
    ],
    'head_of_household': [
        (Decimal('16550'), Decimal('0.10')),
        (Decimal('63100'), Decimal('0.12')),
        (Decimal('100500'), Decimal('0.22')),
        (Decimal('191950'), Decimal('0.24')),
        (Decimal('243700'), Decimal('0.32')),
        (Decimal('609350'), Decimal('0.35')),
        (float('inf'), Decimal('0.37'))
    ]
}

# Standard Deductions 2025
STANDARD_DEDUCTIONS_2025 = {
    'single': Decimal('14600'),
    'married': Decimal('29200'),
    'head_of_household': Decimal('21900'),
    'married_separate': Decimal('14600')
}

# ============================================================================
# STATE TAX RATES & BRACKETS
# ============================================================================

STATE_TAX_DATA = {
    # NO INCOME TAX STATES
    'AK': {'type': 'none'},
    'FL': {'type': 'none'},
    'NV': {'type': 'none'},
    'SD': {'type': 'none'},
    'TN': {'type': 'none'},
    'TX': {'type': 'none'},
    'WA': {'type': 'none'},
    'WY': {'type': 'none'},
    'NH': {'type': 'none'},  # Only dividends/interest
    
    # FLAT TAX STATES
    'AZ': {'type': 'flat', 'rate': Decimal('0.025')},
    'CO': {'type': 'flat', 'rate': Decimal('0.044')},
    'ID': {'type': 'flat', 'rate': Decimal('0.058')},
    'IL': {'type': 'flat', 'rate': Decimal('0.0495')},
    'IN': {'type': 'flat', 'rate': Decimal('0.0315')},
    'KY': {'type': 'flat', 'rate': Decimal('0.045')},
    'MA': {'type': 'flat', 'rate': Decimal('0.05')},
    'MI': {'type': 'flat', 'rate': Decimal('0.0425')},
    'NC': {'type': 'flat', 'rate': Decimal('0.0475')},
    'PA': {'type': 'flat', 'rate': Decimal('0.0307')},
    'UT': {'type': 'flat', 'rate': Decimal('0.0465')},
    
    # PROGRESSIVE TAX STATES
    'AL': {
        'type': 'progressive',
        'brackets': [
            (Decimal('500'), Decimal('0.02')),
            (Decimal('3000'), Decimal('0.04')),
            (float('inf'), Decimal('0.05'))
        ]
    },
    'AR': {
        'type': 'progressive',
        'brackets': [
            (Decimal('5100'), Decimal('0.02')),
            (Decimal('10300'), Decimal('0.04')),
            (Decimal('14600'), Decimal('0.05')),
            (float('inf'), Decimal('0.059'))
        ]
    },
    'CA': {
        'type': 'progressive',
        'brackets': [
            (Decimal('10412'), Decimal('0.01')),
            (Decimal('24684'), Decimal('0.02')),
            (Decimal('38959'), Decimal('0.04')),
            (Decimal('54081'), Decimal('0.06')),
            (Decimal('68350'), Decimal('0.08')),
            (Decimal('349137'), Decimal('0.093')),
            (Decimal('418961'), Decimal('0.103')),
            (Decimal('698271'), Decimal('0.113')),
            (float('inf'), Decimal('0.123'))
        ],
        'sdi': True,
        'sdi_rate': Decimal('0.009'),
        'sdi_wage_base': Decimal('153164')
    },
    'CT': {
        'type': 'progressive',
        'brackets': [
            (Decimal('10000'), Decimal('0.03')),
            (Decimal('50000'), Decimal('0.05')),
            (Decimal('100000'), Decimal('0.055')),
            (Decimal('200000'), Decimal('0.06')),
            (Decimal('250000'), Decimal('0.065')),
            (Decimal('500000'), Decimal('0.069')),
            (float('inf'), Decimal('0.0699'))
        ]
    },
    'DE': {
        'type': 'progressive',
        'brackets': [
            (Decimal('2000'), Decimal('0')),
            (Decimal('5000'), Decimal('0.022')),
            (Decimal('10000'), Decimal('0.039')),
            (Decimal('20000'), Decimal('0.048')),
            (Decimal('25000'), Decimal('0.052')),
            (Decimal('60000'), Decimal('0.0555')),
            (float('inf'), Decimal('0.066'))
        ]
    },
    'GA': {
        'type': 'progressive',
        'brackets': [
            (Decimal('750'), Decimal('0.01')),
            (Decimal('2250'), Decimal('0.02')),
            (Decimal('3750'), Decimal('0.03')),
            (Decimal('5250'), Decimal('0.04')),
            (Decimal('7000'), Decimal('0.05')),
            (float('inf'), Decimal('0.0575'))
        ]
    },
    'HI': {
        'type': 'progressive',
        'brackets': [
            (Decimal('2400'), Decimal('0.014')),
            (Decimal('4800'), Decimal('0.032')),
            (Decimal('9600'), Decimal('0.055')),
            (Decimal('14400'), Decimal('0.064')),
            (Decimal('19200'), Decimal('0.068')),
            (Decimal('24000'), Decimal('0.072')),
            (Decimal('36000'), Decimal('0.076')),
            (Decimal('48000'), Decimal('0.079')),
            (Decimal('150000'), Decimal('0.0825')),
            (Decimal('175000'), Decimal('0.09')),
            (Decimal('200000'), Decimal('0.10')),
            (float('inf'), Decimal('0.11'))
        ]
    },
    'IA': {
        'type': 'progressive',
        'brackets': [
            (Decimal('6000'), Decimal('0.033')),
            (Decimal('30000'), Decimal('0.0495')),
            (Decimal('75000'), Decimal('0.0525')),
            (float('inf'), Decimal('0.06'))
        ]
    },
    'KS': {
        'type': 'progressive',
        'brackets': [
            (Decimal('15000'), Decimal('0.031')),
            (Decimal('30000'), Decimal('0.0525')),
            (float('inf'), Decimal('0.057'))
        ]
    },
    'LA': {
        'type': 'progressive',
        'brackets': [
            (Decimal('12500'), Decimal('0.0185')),
            (Decimal('50000'), Decimal('0.035')),
            (float('inf'), Decimal('0.0425'))
        ]
    },
    'MD': {
        'type': 'progressive',
        'brackets': [
            (Decimal('1000'), Decimal('0.02')),
            (Decimal('2000'), Decimal('0.03')),
            (Decimal('3000'), Decimal('0.04')),
            (Decimal('100000'), Decimal('0.0475')),
            (Decimal('125000'), Decimal('0.05')),
            (Decimal('150000'), Decimal('0.0525')),
            (Decimal('250000'), Decimal('0.055')),
            (float('inf'), Decimal('0.0575'))
        ]
    },
    'ME': {
        'type': 'progressive',
        'brackets': [
            (Decimal('24500'), Decimal('0.058')),
            (Decimal('58050'), Decimal('0.0675')),
            (float('inf'), Decimal('0.0715'))
        ]
    },
    'MN': {
        'type': 'progressive',
        'brackets': [
            (Decimal('29270'), Decimal('0.0535')),
            (Decimal('96360'), Decimal('0.068')),
            (Decimal('179970'), Decimal('0.0785')),
            (float('inf'), Decimal('0.0985'))
        ]
    },
    'MO': {
        'type': 'progressive',
        'brackets': [
            (Decimal('1207'), Decimal('0.015')),
            (Decimal('2414'), Decimal('0.02')),
            (Decimal('3621'), Decimal('0.025')),
            (Decimal('4828'), Decimal('0.03')),
            (Decimal('6035'), Decimal('0.035')),
            (Decimal('7242'), Decimal('0.04')),
            (Decimal('8449'), Decimal('0.045')),
            (float('inf'), Decimal('0.0495'))
        ]
    },
    'MS': {
        'type': 'progressive',
        'brackets': [
            (Decimal('5000'), Decimal('0.03')),
            (Decimal('10000'), Decimal('0.04')),
            (float('inf'), Decimal('0.05'))
        ]
    },
    'MT': {
        'type': 'progressive',
        'brackets': [
            (Decimal('20500'), Decimal('0.0475')),
            (Decimal('52500'), Decimal('0.0575')),
            (float('inf'), Decimal('0.0675'))
        ]
    },
    'NE': {
        'type': 'progressive',
        'brackets': [
            (Decimal('3700'), Decimal('0.0246')),
            (Decimal('22170'), Decimal('0.0351')),
            (Decimal('35730'), Decimal('0.0501')),
            (float('inf'), Decimal('0.0664'))
        ]
    },
    'NJ': {
        'type': 'progressive',
        'brackets': [
            (Decimal('20000'), Decimal('0.014')),
            (Decimal('35000'), Decimal('0.0175')),
            (Decimal('40000'), Decimal('0.035')),
            (Decimal('75000'), Decimal('0.05525')),
            (Decimal('500000'), Decimal('0.0637')),
            (Decimal('1000000'), Decimal('0.0897')),
            (float('inf'), Decimal('0.1075'))
        ],
        'sdi': True,
        'sdi_rate': Decimal('0.0047'),
        'sdi_wage_base': Decimal('161400')
    },
    'NM': {
        'type': 'progressive',
        'brackets': [
            (Decimal('5500'), Decimal('0.017')),
            (Decimal('11000'), Decimal('0.032')),
            (Decimal('16000'), Decimal('0.047')),
            (Decimal('210000'), Decimal('0.049')),
            (float('inf'), Decimal('0.059'))
        ]
    },
    'NY': {
        'type': 'progressive',
        'brackets': [
            (Decimal('8500'), Decimal('0.04')),
            (Decimal('11700'), Decimal('0.045')),
            (Decimal('13900'), Decimal('0.0525')),
            (Decimal('80650'), Decimal('0.055')),
            (Decimal('215400'), Decimal('0.06')),
            (Decimal('1077550'), Decimal('0.0685')),
            (Decimal('5000000'), Decimal('0.0965')),
            (Decimal('25000000'), Decimal('0.103')),
            (float('inf'), Decimal('0.109'))
        ]
    },
    'ND': {
        'type': 'progressive',
        'brackets': [
            (Decimal('44725'), Decimal('0.0105')),
            (Decimal('108300'), Decimal('0.0224')),
            (Decimal('232950'), Decimal('0.0254')),
            (float('inf'), Decimal('0.0285'))
        ]
    },
    'OH': {
        'type': 'progressive',
        'brackets': [
            (Decimal('26050'), Decimal('0.0265')),
            (Decimal('46100'), Decimal('0.0307')),
            (Decimal('92150'), Decimal('0.0359')),
            (Decimal('115300'), Decimal('0.0399')),
            (float('inf'), Decimal('0.0399'))
        ]
    },
    'OK': {
        'type': 'progressive',
        'brackets': [
            (Decimal('1000'), Decimal('0.0025')),
            (Decimal('2500'), Decimal('0.0075')),
            (Decimal('3750'), Decimal('0.0175')),
            (Decimal('4900'), Decimal('0.0275')),
            (Decimal('7200'), Decimal('0.0375')),
            (float('inf'), Decimal('0.0475'))
        ]
    },
    'OR': {
        'type': 'progressive',
        'brackets': [
            (Decimal('4050'), Decimal('0.0475')),
            (Decimal('10200'), Decimal('0.0675')),
            (Decimal('125000'), Decimal('0.0875')),
            (float('inf'), Decimal('0.099'))
        ],
        'transit_tax': Decimal('0.001')  # Metro area
    },
    'RI': {
        'type': 'progressive',
        'brackets': [
            (Decimal('73450'), Decimal('0.0375')),
            (Decimal('166950'), Decimal('0.0475')),
            (float('inf'), Decimal('0.0599'))
        ],
        'sdi': True,
        'sdi_rate': Decimal('0.013'),
        'sdi_wage_base': Decimal('84000')
    },
    'SC': {
        'type': 'progressive',
        'brackets': [
            (Decimal('3200'), Decimal('0.0097')),
            (Decimal('16040'), Decimal('0.04')),
            (float('inf'), Decimal('0.064'))
        ]
    },
    'VT': {
        'type': 'progressive',
        'brackets': [
            (Decimal('42150'), Decimal('0.0335')),
            (Decimal('102200'), Decimal('0.066')),
            (Decimal('213150'), Decimal('0.076')),
            (float('inf'), Decimal('0.0875'))
        ]
    },
    'VA': {
        'type': 'progressive',
        'brackets': [
            (Decimal('3000'), Decimal('0.02')),
            (Decimal('5000'), Decimal('0.03')),
            (Decimal('17000'), Decimal('0.05')),
            (float('inf'), Decimal('0.0575'))
        ]
    },
    'WV': {
        'type': 'progressive',
        'brackets': [
            (Decimal('10000'), Decimal('0.024')),
            (Decimal('25000'), Decimal('0.032')),
            (Decimal('40000'), Decimal('0.045')),
            (Decimal('60000'), Decimal('0.06')),
            (float('inf'), Decimal('0.065'))
        ]
    },
    'WI': {
        'type': 'progressive',
        'brackets': [
            (Decimal('13810'), Decimal('0.0354')),
            (Decimal('27630'), Decimal('0.0465')),
            (Decimal('304170'), Decimal('0.0627')),
            (float('inf'), Decimal('0.0765'))
        ]
    },
    'DC': {
        'type': 'progressive',
        'brackets': [
            (Decimal('10000'), Decimal('0.04')),
            (Decimal('40000'), Decimal('0.06')),
            (Decimal('60000'), Decimal('0.065')),
            (Decimal('250000'), Decimal('0.085')),
            (Decimal('500000'), Decimal('0.0925')),
            (Decimal('1000000'), Decimal('0.0975')),
            (float('inf'), Decimal('0.1075'))
        ]
    }
}

# ============================================================================
# LOCAL TAX JURISDICTIONS
# ============================================================================

LOCAL_TAX_RATES = {
    'NY': {
        'New York City': Decimal('0.03876'),  # Resident rate
        'Yonkers': Decimal('0.016875')  # Resident rate
    },
    'PA': {
        'Philadelphia': Decimal('0.03712'),
        'Pittsburgh': Decimal('0.03')
    },
    'OH': {
        'Columbus': Decimal('0.025'),
        'Cleveland': Decimal('0.025'),
        'Cincinnati': Decimal('0.0192')
    },
    'MI': {
        'Detroit': Decimal('0.024')
    },
    'MD': {
        'Baltimore': Decimal('0.032')
    },
    'KY': {
        'Louisville': Decimal('0.0225')
    },
    'OR': {
        'Multnomah County': Decimal('0.015'),  # Metro tax
        'Tri-Met': Decimal('0.0075')
    }
}

# ============================================================================
# TAX CALCULATION FUNCTIONS
# ============================================================================

def calculate_federal_income_tax(gross_pay, filing_status, pay_frequency, allowances=0, additional_withholding=0, ytd_gross=0):
    """Calculate federal income tax withholding"""
    
    gross = Decimal(str(gross_pay))
    additional = Decimal(str(additional_withholding))
    ytd = Decimal(str(ytd_gross))
    
    # Annualize based on pay frequency
    frequency_multiplier = {
        'weekly': 52,
        'biweekly': 26,
        'semimonthly': 24,
        'monthly': 12
    }
    multiplier = Decimal(str(frequency_multiplier.get(pay_frequency, 26)))
    annualized_gross = gross * multiplier
    
    # Get standard deduction
    status_map = {
        'single': 'single',
        'married': 'married',
        'married_separate': 'married_separate',
        'head_of_household': 'head_of_household'
    }
    mapped_status = status_map.get(filing_status, 'single')
    standard_deduction = STANDARD_DEDUCTIONS_2025.get(mapped_status, STANDARD_DEDUCTIONS_2025['single'])
    
    # Calculate taxable income
    taxable_income = max(Decimal('0'), annualized_gross - standard_deduction)
    
    # Calculate tax using brackets
    brackets = FEDERAL_TAX_BRACKETS_2025.get(mapped_status, FEDERAL_TAX_BRACKETS_2025['single'])
    annual_tax = Decimal('0')
    previous_bracket = Decimal('0')
    
    for bracket_limit, rate in brackets:
        bracket_limit = Decimal(str(bracket_limit)) if bracket_limit != float('inf') else Decimal('999999999')
        
        if taxable_income > previous_bracket:
            taxable_in_bracket = min(taxable_income, bracket_limit) - previous_bracket
            annual_tax += taxable_in_bracket * rate
            previous_bracket = bracket_limit
        
        if taxable_income <= bracket_limit:
            break
    
    # Convert to per-period tax
    period_tax = (annual_tax / multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # Add additional withholding
    total_tax = period_tax + additional
    
    return float(total_tax)


def calculate_social_security_tax(gross_pay, ytd_ss_wages):
    """Calculate Social Security tax (6.2% up to wage base)"""
    
    gross = Decimal(str(gross_pay))
    ytd = Decimal(str(ytd_ss_wages))
    
    # Check if already exceeded wage base
    if ytd >= SOCIAL_SECURITY_WAGE_BASE:
        return 0.0
    
    # Calculate taxable amount
    remaining_taxable = SOCIAL_SECURITY_WAGE_BASE - ytd
    taxable_this_period = min(gross, remaining_taxable)
    
    ss_tax = (taxable_this_period * SOCIAL_SECURITY_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return float(ss_tax)


def calculate_medicare_tax(gross_pay, filing_status, ytd_gross):
    """Calculate Medicare tax (1.45% + 0.9% over threshold)"""
    
    gross = Decimal(str(gross_pay))
    ytd = Decimal(str(ytd_gross))
    
    # Regular Medicare (1.45%)
    medicare_tax = gross * MEDICARE_RATE
    
    # Additional Medicare (0.9% over threshold)
    threshold = ADDITIONAL_MEDICARE_THRESHOLD_MARRIED if filing_status == 'married' else ADDITIONAL_MEDICARE_THRESHOLD_SINGLE
    
    additional_medicare = Decimal('0')
    if ytd + gross > threshold:
        if ytd >= threshold:
            # All of this pay is subject to additional Medicare
            additional_medicare = gross * ADDITIONAL_MEDICARE_RATE
        else:
            # Part of this pay exceeds threshold
            excess = (ytd + gross) - threshold
            additional_medicare = excess * ADDITIONAL_MEDICARE_RATE
    
    total = (medicare_tax + additional_medicare).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return float(total)


def calculate_state_income_tax(gross_pay, state, filing_status, pay_frequency, allowances=0, additional_withholding=0):
    """Calculate state income tax"""
    
    if state not in STATE_TAX_DATA:
        return 0.0
    
    state_data = STATE_TAX_DATA[state]
    gross = Decimal(str(gross_pay))
    additional = Decimal(str(additional_withholding))
    
    # No tax states
    if state_data['type'] == 'none':
        return 0.0
    
    # Flat tax states
    if state_data['type'] == 'flat':
        rate = state_data['rate']
        state_tax = gross * rate + additional
        return float(state_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    
    # Progressive tax states
    if state_data['type'] == 'progressive':
        # Annualize
        frequency_multiplier = {
            'weekly': 52,
            'biweekly': 26,
            'semimonthly': 24,
            'monthly': 12
        }
        multiplier = Decimal(str(frequency_multiplier.get(pay_frequency, 26)))
        annualized_gross = gross * multiplier
        
        # Calculate using brackets
        brackets = state_data['brackets']
        annual_tax = Decimal('0')
        previous_bracket = Decimal('0')
        
        for bracket_limit, rate in brackets:
            bracket_limit = Decimal(str(bracket_limit)) if bracket_limit != float('inf') else Decimal('999999999')
            
            if annualized_gross > previous_bracket:
                taxable_in_bracket = min(annualized_gross, bracket_limit) - previous_bracket
                annual_tax += taxable_in_bracket * rate
                previous_bracket = bracket_limit
            
            if annualized_gross <= bracket_limit:
                break
        
        # Convert to per-period
        period_tax = (annual_tax / multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_tax = period_tax + additional
        
        return float(total_tax)
    
    return 0.0


def calculate_state_disability_tax(gross_pay, state, ytd_gross=0):
    """Calculate State Disability Insurance (CA, NY, NJ, RI, HI)"""
    
    if state not in STATE_TAX_DATA:
        return 0.0
    
    state_data = STATE_TAX_DATA[state]
    
    if not state_data.get('sdi', False):
        return 0.0
    
    gross = Decimal(str(gross_pay))
    ytd = Decimal(str(ytd_gross))
    sdi_rate = state_data['sdi_rate']
    wage_base = state_data.get('sdi_wage_base', Decimal('999999999'))
    
    # Check if exceeded wage base
    if ytd >= wage_base:
        return 0.0
    
    # Calculate taxable amount
    remaining_taxable = wage_base - ytd
    taxable_this_period = min(gross, remaining_taxable)
    
    sdi_tax = (taxable_this_period * sdi_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return float(sdi_tax)


def calculate_local_income_tax(gross_pay, state, jurisdiction):
    """Calculate local income tax"""
    
    if state not in LOCAL_TAX_RATES:
        return 0.0
    
    if jurisdiction not in LOCAL_TAX_RATES[state]:
        return 0.0
    
    gross = Decimal(str(gross_pay))
    rate = LOCAL_TAX_RATES[state][jurisdiction]
    
    local_tax = (gross * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return float(local_tax)


def calculate_all_taxes(gross_pay, state, filing_status='single', pay_frequency='biweekly', 
                       allowances=0, additional_withholding=0, ytd_gross=0, ytd_ss_wages=0,
                       local_jurisdiction=None):
    """
    Calculate all taxes for a paystub
    
    Returns dict with all tax calculations
    """
    
    federal_tax = calculate_federal_income_tax(
        gross_pay, filing_status, pay_frequency, allowances, additional_withholding, ytd_gross
    )
    
    ss_tax = calculate_social_security_tax(gross_pay, ytd_ss_wages)
    
    medicare_tax = calculate_medicare_tax(gross_pay, filing_status, ytd_gross)
    
    state_tax = calculate_state_income_tax(
        gross_pay, state, filing_status, pay_frequency, allowances, additional_withholding
    )
    
    sdi_tax = calculate_state_disability_tax(gross_pay, state, ytd_gross)
    
    local_tax = 0.0
    if local_jurisdiction:
        local_tax = calculate_local_income_tax(gross_pay, state, local_jurisdiction)
    
    return {
        'federal_income_tax': federal_tax,
        'social_security_tax': ss_tax,
        'medicare_tax': medicare_tax,
        'state_income_tax': state_tax,
        'state_disability_tax': sdi_tax,
        'local_income_tax': local_tax,
        'total_federal': federal_tax + ss_tax + medicare_tax,
        'total_state': state_tax + sdi_tax,
        'total_local': local_tax,
        'total_taxes': federal_tax + ss_tax + medicare_tax + state_tax + sdi_tax + local_tax
    }


def get_available_local_jurisdictions(state):
    """Get list of available local tax jurisdictions for a state"""
    return list(LOCAL_TAX_RATES.get(state, {}).keys())


def get_state_info(state):
    """Get state tax information"""
    if state not in STATE_TAX_DATA:
        return None
    
    data = STATE_TAX_DATA[state]
    
    return {
        'state_code': state,
        'tax_type': data['type'],
        'has_state_tax': data['type'] != 'none',
        'has_sdi': data.get('sdi', False),
        'has_local_tax': state in LOCAL_TAX_RATES,
        'local_jurisdictions': get_available_local_jurisdictions(state)
    }
