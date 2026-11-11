import { FileSignature, Globe2, LayoutDashboard, Menu } from 'lucide-react';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { abrirModulo } from '@/lib/navigation';

export default function WorkspaceMenu() {
  return <DropdownMenu>
    <DropdownMenuTrigger className="shell-icon-button" aria-label="Abrir bandeja de trabajo" title="Bandeja de trabajo">
      <Menu size={20} aria-hidden />
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="workspace-menu">
      <DropdownMenuLabel>Tu espacio de trabajo</DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={() => abrirModulo('licitaciones-obra')}><LayoutDashboard aria-hidden />Workspace</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => abrirModulo('tezcatlipoca-hub')}><Globe2 aria-hidden />Tezcatlipoca</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => abrirModulo('documentos-firma')}><FileSignature aria-hidden />Firma / Field SAT</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}
