# trailbot-cli

Unofficial command-line interface for [Trailbot](https://trailbot.com) mountain bike trail conditions. Check trail status, find open trails near you, and search 300+ systems across the US and Canada — all from your terminal.

## Install

```bash
pip install trailbot-cli
```

Or from source:

```bash
git clone https://github.com/bobertoni/trailbot-cli
cd trailbot-cli
pip install -e .
```

## Usage

**Get current status for a trail:**
```bash
trailbot status detroit-mountain
```
```
Detroit Mountain — Detroit Lakes, MN
Status: 🔴 Closed
Tags:   wet
Updated: May 23 02:03 AM CDT

Rain has moved in for a good soaker. Keep eyes on trail report for updates
on Opening Day for lift service & rentals Tomorrow, Saturday May 23rd.
Delayed trail opening may be possible with the wet conditions.
```

**Find open trails near you:**
```bash
trailbot near 44.85,-93.52 --radius 75
```

**Show all trails near you (open + closed):**
```bash
trailbot near 44.85,-93.52 --radius 100 --all
```

**List all open trails in a state:**
```bash
trailbot open --state MN
```

**Search trail systems:**
```bash
trailbot search "spirit mountain"
trailbot search giants --state MN
```

## Notes

This tool uses Trailbot's internal Next.js data API. It is unofficial and unaffiliated with Trailbot Inc. The API is undocumented and may change without notice. Trail status data is provided directly by trail maintainers via the Trailbot platform.

If you find this useful, consider supporting your local trail association.

## License

MIT
