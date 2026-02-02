import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Menu, BarChart3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
  navigationMenuTriggerStyle,
} from '@/components/ui/navigation-menu'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { ThemeToggle } from './theme-toggle'
import { NAV_ITEMS, ROUTES } from '@/lib/constants'
import { cn } from '@/lib/utils'

export function TopNav() {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const isActive = (href: string) => {
    if (href === ROUTES.DASHBOARD) {
      return location.pathname === href
    }
    return location.pathname.startsWith(href)
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center">
        {/* Logo */}
        <Link to={ROUTES.DASHBOARD} className="mr-6 flex items-center space-x-2">
          <BarChart3 className="h-6 w-6" />
          <span className="hidden font-bold sm:inline-block">ForecastLab</span>
        </Link>

        {/* Desktop Navigation */}
        <NavigationMenu className="hidden md:flex">
          <NavigationMenuList>
            {NAV_ITEMS.map((item) => (
              <NavigationMenuItem key={item.label}>
                {'items' in item ? (
                  <>
                    <NavigationMenuTrigger>{item.label}</NavigationMenuTrigger>
                    <NavigationMenuContent>
                      <ul className="grid w-[200px] gap-1 p-2">
                        {item.items.map((subItem) => (
                          <li key={subItem.href}>
                            <NavigationMenuLink asChild>
                              <Link
                                to={subItem.href}
                                className={cn(
                                  'block select-none rounded-md p-2 text-sm leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground',
                                  isActive(subItem.href) && 'bg-accent/50'
                                )}
                              >
                                {subItem.label}
                              </Link>
                            </NavigationMenuLink>
                          </li>
                        ))}
                      </ul>
                    </NavigationMenuContent>
                  </>
                ) : (
                  <Link
                    to={item.href}
                    className={cn(
                      navigationMenuTriggerStyle(),
                      isActive(item.href) && 'bg-accent/50'
                    )}
                  >
                    {item.label}
                  </Link>
                )}
              </NavigationMenuItem>
            ))}
          </NavigationMenuList>
        </NavigationMenu>

        {/* Right side controls */}
        <div className="flex flex-1 items-center justify-end space-x-2">
          <ThemeToggle />

          {/* Mobile Menu Button */}
          <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[300px] sm:w-[400px]">
              <SheetHeader>
                <SheetTitle className="flex items-center space-x-2">
                  <BarChart3 className="h-5 w-5" />
                  <span>ForecastLab</span>
                </SheetTitle>
              </SheetHeader>
              <nav className="flex flex-col gap-4 mt-6">
                {NAV_ITEMS.map((item) => (
                  <div key={item.label}>
                    {'items' in item ? (
                      <div className="space-y-2">
                        <h4 className="font-medium text-sm text-muted-foreground px-2">
                          {item.label}
                        </h4>
                        <div className="space-y-1">
                          {item.items.map((subItem) => (
                            <Link
                              key={subItem.href}
                              to={subItem.href}
                              onClick={() => setMobileMenuOpen(false)}
                              className={cn(
                                'block rounded-md px-2 py-1.5 text-sm hover:bg-accent',
                                isActive(subItem.href) && 'bg-accent/50 font-medium'
                              )}
                            >
                              {subItem.label}
                            </Link>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <Link
                        to={item.href}
                        onClick={() => setMobileMenuOpen(false)}
                        className={cn(
                          'block rounded-md px-2 py-1.5 text-sm font-medium hover:bg-accent',
                          isActive(item.href) && 'bg-accent/50'
                        )}
                      >
                        {item.label}
                      </Link>
                    )}
                  </div>
                ))}
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  )
}
