# StudyRoute Domain Setup Report

## Summary

- Vercel project: `studyroute`
- Added domain: `studyroute.co.kr`
- Added www domain: `www.studyroute.co.kr`
- DNS provider detected: Gabia nameservers
- DNS modified automatically: No
- Deployment triggered: No
- GitHub modified: No

## Vercel Domain Status

Both domains were added to the Vercel project, but DNS is not configured yet.

- `studyroute.co.kr`: added, attached to project, DNS action required
- `www.studyroute.co.kr`: added, attached to project, DNS action required

Current nameservers detected by Vercel:

- `ns.gabia.co.kr`
- `ns.gabia.net`
- `ns1.gabia.co.kr`

## DNS Records To Enter In Gabia

Use the records below in Gabia DNS. Leave Priority empty unless Gabia requires a value. Use Gabia default TTL unless a custom TTL is required.

| Host | Type | Value | Priority | TTL |
|---|---|---|---|---|
| `@` | `A` | `216.198.79.1` | - | Default |
| `@` | `A` | `64.29.17.1` | - | Default |
| `www` | `CNAME` | `7937aecf790ba652.vercel-dns-017.com.` | - | Default |

## Not Required Now

Vercel did not require these records in the current verification result:

- `AAAA`
- `ALIAS`
- `TXT`

## www Requirement

`www.studyroute.co.kr` should be added if you want both of these to work:

- `https://studyroute.co.kr`
- `https://www.studyroute.co.kr`

It has already been added to the Vercel project. Gabia still needs the `www` CNAME record above.

## SSL Status

SSL is not active yet because DNS is not configured.

After the Gabia DNS records are added and propagated, Vercel should automatically verify the domains and issue SSL certificates. No manual certificate upload is required.

## Next Work

1. In Gabia DNS, add the two A records for `studyroute.co.kr`.
2. In Gabia DNS, add the CNAME record for `www.studyroute.co.kr`.
3. Wait for DNS propagation.
4. Re-run Vercel domain verification for:
   - `studyroute.co.kr`
   - `www.studyroute.co.kr`
5. Confirm both domains show valid DNS and SSL.

## Conclusion

DNS 자동 수정은 하지 않았습니다. 가비아에 입력해야 하는 DNS 값만 추출했습니다.
