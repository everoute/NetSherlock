# Mock Diagnosis Data

This project includes mock diagnosis data based on real measurements from the `measurement-*` directories. This allows you to develop and test the UI without a running backend API.

## Mock Data Features

The mock data includes:

- **4 Completed Diagnoses** - Real measurement results with full reports
  - VM Latency: From measurement-20260204-175008
  - VM Drop Detection: From measurement-20260204-175437
  - System Latency: From measurement-20260204-175710
  - VM Cross-Node Latency: From measurement-20260204-180934

- **3 In-Progress/Pending Diagnoses** - Shows various diagnosis states
  - Running diagnosis
  - Pending diagnosis
  - Waiting (interactive mode)

- **1 Error Diagnosis** - Demonstrates error handling

## Enabling Mock Data

Mock data is controlled via the `VITE_USE_MOCK_DATA` environment variable:

### Development (Mock Data Enabled)

```bash
# Edit .env to enable mock data
VITE_USE_MOCK_DATA=true
VITE_API_URL=http://localhost:8000

npm run dev
```

### Production (Real API)

```bash
VITE_USE_MOCK_DATA=false
VITE_API_URL=http://your-api-server:8000

npm run build
```

## Mock Data Structure

The mock data is defined in `src/lib/mockData.ts` and includes:

```typescript
interface DiagnosisResponse {
  diagnosis_id: string           // Unique identifier
  status: DiagnosisStatus        // pending, running, waiting, completed, error, etc.
  timestamp: string              // When diagnosis was created
  started_at?: string            // When diagnosis started
  completed_at?: string          // When diagnosis finished
  mode?: string                  // 'autonomous' or 'interactive'
  summary?: string               // Brief summary
  root_cause?: RootCause        // Root cause analysis (if completed)
  recommendations?: Recommendation[] // Action items
  markdown_report?: string       // Full detailed report
  error?: string                // Error message (if failed)
}
```

## Using Mock Data in Components

Mock data is automatically used when `VITE_USE_MOCK_DATA=true`:

```typescript
// In any component
import { api } from '@/lib/api'

// Get a single diagnosis
const diagnosis = await api.getDiagnosis('diag-20260204-175008-vm-latency')

// List diagnoses
const diagnoses = await api.listDiagnoses({ limit: 100 })

// The API client automatically switches between mock and real data
// based on the VITE_USE_MOCK_DATA environment variable
```

## Available Mock Diagnoses

### Completed Diagnoses

1. **VM Latency Analysis**
   - ID: `diag-20260204-175008-vm-latency`
   - Type: Latency measurement
   - Root Cause: vhost_processing (Receiver Host OVS)
   - Confidence: 92%

2. **VM Drop Detection**
   - ID: `diag-20260204-175437-vm-drops`
   - Type: Drop detection
   - Root Cause: None (no drops found)
   - Confidence: 98%

3. **System Latency Analysis**
   - ID: `diag-20260204-175710-system-latency`
   - Type: System latency
   - Root Cause: host_internal (Sender Host Processing)
   - Confidence: 96%

4. **VM Cross-Node Latency**
   - ID: `diag-20260204-180934-vm-cross-node`
   - Type: Cross-node latency
   - Root Cause: vhost_processing
   - Confidence: 88%

### Active Diagnoses

5. **Running Diagnosis**
   - ID: `diag-20260205-120000-new-latency`
   - Status: running

6. **Pending Diagnosis**
   - ID: `diag-20260205-120100-pending-drops`
   - Status: pending

7. **Interactive Diagnosis**
   - ID: `diag-20260205-115900-interactive`
   - Status: waiting

8. **Failed Diagnosis**
   - ID: `diag-20260205-110000-failed`
   - Status: error

## Adding More Mock Data

To add more mock data:

1. Edit `src/lib/mockData.ts`
2. Add a new entry to the `mockDiagnoses` array
3. Follow the `DiagnosisResponse` interface structure
4. Use real measurement reports as reference for realistic data

## Network Simulation

Mock data includes simulated network delays:
- `getDiagnosis()`: 300ms delay
- `listDiagnoses()`: 500ms delay

This helps test loading states and async behavior in the UI.

## Testing Tips

- **Test Completed Diagnoses**: View full reports, root cause analysis, and recommendations
- **Test Loading States**: Monitor the "Running" diagnosis in the UI
- **Test Error Handling**: Check how errors are displayed
- **Test List Filtering**: Use different status filters in the Tasks/Reports pages
- **Test Detail Views**: Navigate between list and detail views

## Switching to Real API

To use the real backend API:

1. Update `.env`:
   ```
   VITE_USE_MOCK_DATA=false
   VITE_API_URL=http://your-api-server:8000
   ```

2. Start your backend service
3. Restart the development server: `npm run dev`

The API client will automatically use the real endpoints.
