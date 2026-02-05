# Data Processor Memory - MDO Attack Simulation Project

## Parquet Implementation for Power BI

### Schema Optimization Strategy
Power BI performs best with Parquet files that have:
- **Datetime columns**: datetime64 with UTC timezone, millisecond precision
- **Count columns**: int32 (sufficient range, better compression than int64)
- **String columns**: Explicit string dtype (not generic object)
- **Timestamps**: INT64 encoding (not deprecated INT96)
- **Compression**: Snappy (fast decompression, good balance)

### Data Pipeline Architecture
- **Raw container**: JSON files for archival and debugging
- **Curated container**: Parquet files optimized for Power BI consumption
- **File naming**: `{api_name}/{snapshot_date}/{api_name}.parquet`

### Type Conversion Rules Applied
1. Columns with "date" or "datetime" in name → datetime64[ns, UTC]
2. Columns ending in "Count" or containing "count" → int32
3. Remaining object columns → string dtype
4. All conversions use error='coerce' to handle malformed data gracefully

### Dependencies Added
- pyarrow==14.0.1 (Parquet engine)
- pandas==2.1.4 (DataFrame operations)

### Performance Considerations
- Snappy compression provides 2-5x compression ratio
- INT64 timestamps are native to Power BI (no conversion overhead)
- Explicit type casting eliminates Power BI's type inference overhead
- In-memory buffer approach (io.BytesIO) avoids temp file I/O
