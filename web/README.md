# NetSherlock UI

Web-based dashboard for managing and monitoring AI-driven network diagnostic tasks.

## Features

- **Task Management**: Create, monitor, and manage network diagnosis tasks
- **Real-time Status**: Live updates for running diagnostics with log streaming
- **Report Viewing**: Comprehensive reports with root cause analysis and recommendations
- **Responsive Design**: Works on both desktop and tablet devices

## Tech Stack

- React 19 + TypeScript
- Vite 7 (build tool)
- React Router 7 (routing)
- Tailwind CSS v4 (styling)
- lucide-react (icons)
- react-markdown (markdown rendering)

## Getting Started

### Prerequisites

- Node.js 18+ or Bun
- NetSherlock backend API running

### Installation

```bash
# Install dependencies
npm install
# or
bun install
```

### Configuration

Create a `.env` file in the web directory:

```env
VITE_API_URL=http://localhost:8080
VITE_API_KEY=your-api-key-here
```

### Development

```bash
# Start development server
npm run dev
# or
bun run dev
```

The application will be available at `http://localhost:3000`

### Production Build

```bash
# Build for production
npm run build
# or
bun run build

# Preview production build
npm run preview
# or
bun run preview
```

## Project Structure

```
web/
├── src/
│   ├── components/      # Shared UI components
│   │   ├── Layout.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Header.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── RootCauseBadge.tsx
│   │   └── ConfidenceBar.tsx
│   ├── pages/          # Page components
│   │   ├── TasksPage.tsx
│   │   ├── TaskDetailPage.tsx
│   │   ├── NewTaskPage.tsx
│   │   ├── ReportsPage.tsx
│   │   └── ReportDetailPage.tsx
│   ├── lib/            # Utilities and API client
│   │   ├── api.ts
│   │   └── utils.ts
│   ├── types/          # TypeScript type definitions
│   │   └── index.ts
│   ├── App.tsx         # Main app component with routing
│   ├── main.tsx        # App entry point
│   └── index.css       # Global styles
├── public/             # Static assets
├── index.html          # HTML template
├── package.json        # Dependencies and scripts
├── tsconfig.json       # TypeScript configuration
├── vite.config.ts      # Vite configuration
└── tailwind.config.js  # Tailwind CSS configuration
```

## API Integration

The UI communicates with the NetSherlock backend API:

- `GET /health` - Health check
- `POST /diagnose` - Create new diagnosis task
- `GET /diagnose/{id}` - Get task details
- `GET /diagnoses` - List all diagnoses

All requests require the `X-API-Key` header for authentication.

## Development Notes

- Tasks list auto-refreshes every 5 seconds
- Task detail page polls every 2 seconds for running tasks
- API base URL can be configured via `VITE_API_URL` environment variable
- The app uses Vite proxy for development to avoid CORS issues

## License

Copyright (c) 2026 NetSherlock
