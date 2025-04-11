def match_startups(startups, industry, stage, risk_level):
    matches = []
    for startup in startups:
        score = 0
        if industry and startup['industry'] == industry:
            score += 40
        if stage and startup['stage'] == stage:
            score += 30
        if risk_level and startup['risk_level'] == risk_level:
            score += 30
        if score > 0:
            startup_dict = dict(startup)
            startup_dict['compatibility'] = score
            matches.append(startup_dict)
    return sorted(matches, key=lambda x: x['compatibility'], reverse=True)