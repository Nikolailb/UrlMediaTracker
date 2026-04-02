# Chapter Tracker — Frontend

React + TypeScript frontend for the Smart Bookmark & Chapter Tracker.

## Requirements

- Node.js 18+

## Quick start

```powershell
# From repo root:
npm run dev:frontend

# Or directly from this directory:
npm run dev
```

The app will be available at **http://localhost:5173**.  
The Vite dev server proxies all `/api/*` requests to `http://localhost:8000`, so the backend must also be running.

## Start everything at once

From the **repo root**:

```powershell
npm run dev
```

This starts both the backend and the frontend simultaneously using `concurrently`.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run ESLint |

## Project structure

```
src/
  api/
    client.ts         # Base fetch wrapper (proxy-aware, error normalisation)
    items.ts          # All /items endpoint calls
    patterns.ts       # POST /patterns/detect
  components/
    ui/               # Primitive UI components (Button, Input, Dialog, …)
    layout/
      AppLayout.tsx   # Responsive page shell
      Header.tsx      # App bar with Check All + theme toggle
      ThemeToggle.tsx # System / Light / Dark picker
    items/
      ItemList.tsx         # Filter + sort orchestrator
      ItemTable.tsx        # Desktop sortable table
      ItemCards.tsx        # Mobile card grid
      ItemProgress.tsx     # Chapter progress indicator
      ItemActions.tsx      # ⋮ dropdown (open, mark read, check, edit, delete)
      AddItemDialog.tsx    # 2-step add dialog with live pattern preview
      EditItemDialog.tsx   # Edit dialog
      DeleteItemDialog.tsx # Confirm delete dialog
  hooks/
    useTheme.ts          # Theme state + localStorage persistence
    useItems.ts          # TanStack Query hooks for all item operations
    usePatternDetect.ts  # Pattern detection mutation
  lib/
    utils.ts             # cn(), chapterToFloat(), formatDate()
    queryClient.ts       # TanStack QueryClient singleton
  pages/
    ItemsPage.tsx        # Main page
  types/
    api.ts               # TypeScript types mirroring the backend Pydantic schemas
  App.tsx                # Root: QueryClientProvider + Router + Toaster
  main.tsx
  index.css              # Tailwind directives + CSS variable theme
```

## Theming

Dark mode is enabled by default (follows system preference). The user can override via the theme toggle in the header. The choice persists in `localStorage`.  
A small inline script in `index.html` applies the correct class before React mounts to prevent flash of wrong theme.

## Generating types from the OpenAPI schema

Once the backend is running, types can be regenerated automatically:

```powershell
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/schema.ts
```

Replace `src/types/api.ts` imports with `schema.ts` imports as needed.

