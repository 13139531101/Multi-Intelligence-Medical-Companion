import React from "react";
import { Link } from "react-router-dom";

const navItems = [
  { to: "/agents", label: "Agent", hoverColor: "blue-600" },
  { to: "/start_conversations", label: "开始会话", hoverColor: "green-600" },
  { to: "/conversations", label: "会话记录", hoverColor: "green-600" },
  { to: "/events", label: "事件", hoverColor: "purple-600" },
  { to: "/settings", label: "设置", hoverColor: "yellow-500" },
  { to: "/tasks", label: "任务", hoverColor: "red-500" },
];

const NavLink = ({ to, children, hoverColor }) => (
  <Link
    to={to}
    className={`text-gray-600 hover:text-${hoverColor} font-medium`}
  >
    {children}
  </Link>
);

export const Header = () => {
  return (
    <header className="bg-white shadow-md p-4 flex items-center justify-between">
      <div className="text-2xl font-bold text-blue-600">
        <Link to="/">A2A</Link>
      </div>
      <nav className="flex space-x-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            hoverColor={item.hoverColor}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
};

export default Header;