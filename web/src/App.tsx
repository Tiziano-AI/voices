import { StudioShell } from './components/StudioShell';
import { useStudioController } from './hooks/useStudioController';

export default function App() {
  const controller = useStudioController();
  return <StudioShell controller={controller} />;
}
