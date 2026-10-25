import { useEffect, useState } from "react";
import { api } from "../api.js";

/** <datalist id="staff-names"> of active staff, for technician inputs. Failure just means no suggestions. */
export default function StaffDatalist() {
  const [staff, setStaff] = useState([]);
  useEffect(() => { api("/staff").then(setStaff).catch(() => {}); }, []);
  return <datalist id="staff-names">{staff.map((s) => <option key={s.id} value={s.full_name} />)}</datalist>;
}
