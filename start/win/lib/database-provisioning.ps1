function New-BillDatabaseUrl {
    param(
        [Parameter(Mandatory)][string]$Username,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Password,
        [Parameter(Mandatory)][string]$HostName,
        [Parameter(Mandatory)][ValidateRange(1, 65535)][int]$Port,
        [Parameter(Mandatory)][string]$Database
    )
    if ($Database -notmatch '^[a-z][a-z0-9_]*$') { throw 'Invalid MySQL database name.' }
    return 'mysql+asyncmy://{0}:{1}@{2}:{3}/{4}' -f `
        [Uri]::EscapeDataString($Username), [Uri]::EscapeDataString($Password),
        $HostName, $Port, $Database
}

function Set-BillEnvironmentValue {
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Content,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value
    )
    if ($Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw 'Invalid environment variable name.' }
    $pattern = '(?m)^' + [regex]::Escape($Name) + '=.*$'
    $matches = [regex]::Matches($Content, $pattern)
    if ($matches.Count -ne 1) { throw "Expected exactly one $Name entry in the environment file." }

    return [regex]::Replace(
        $Content,
        $pattern,
        [System.Text.RegularExpressions.MatchEvaluator]{
            param($match)
            return $Name + '=' + $Value
        }
    )
}
