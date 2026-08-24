
import main
import inspect

print(f"get_max_years_from_sections is defined in: {inspect.getmodule(main.get_max_years_from_sections).__file__}")

print("\n--- Actual source code being executed ---")
print(inspect.getsource(main.get_max_years_from_sections))

