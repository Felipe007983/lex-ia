import React, { useState, useEffect } from 'react';
import { Lock, User, Search, FileText, Smartphone, Mail, MapPin, Database, LogOut, Calendar, Download, AlertTriangle } from 'lucide-react';
import axios from 'axios';

// Configuração do Axios
const api = axios.create({
    baseURL: 'http://localhost:3000',
});

function App() {
    const [user, setUser] = useState(null);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    // Dashboard Data
    const [contratos, setContratos] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [referenceDates, setReferenceDates] = useState([]);
    const [selectedDate, setSelectedDate] = useState('');
    const [exporting, setExporting] = useState(false);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (token) {
            setUser({ token });
            fetchContratos(token);
            fetchDates(token);
        }
    }, []);

    const fetchContratos = async (token) => {
        try {
            const response = await api.get('/api/contratos', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setContratos(response.data);
        } catch (err) {
            console.error(err);
            if (err.response?.status === 401 || err.response?.status === 403) {
                logout();
            }
        }
    };

    const fetchDates = async (token) => {
        try {
            const response = await api.get('/api/dates', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setReferenceDates(response.data);
        } catch (err) {
            console.error("Erro ao buscar datas", err);
        }
    };

    const handleExport = async () => {
        try {
            setExporting(true);
            const token = localStorage.getItem('token');
            const response = await api.get('/api/export', {
                params: { date: selectedDate },
                headers: { Authorization: `Bearer ${token}` },
                responseType: 'blob',
            });

            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `contratos_${selectedDate || 'todos'}.csv`);
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (err) {
            console.error("Erro ao exportar", err);
            alert("Erro ao exportar CSV");
        } finally {
            setExporting(false);
        }
    };

    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const response = await api.post('/login', { username, password });
            const { token } = response.data;

            localStorage.setItem('token', token);
            setUser({ username, token });
            fetchContratos(token);
            fetchDates(token);
        } catch (err) {
            setError('Credenciais inválidas. Tente novamente.');
        } finally {
            setLoading(false);
        }
    };

    const logout = () => {
        localStorage.removeItem('token');
        setUser(null);
        setContratos([]);
    };

    const filteredContratos = contratos.filter(c => {
        const matchesSearch = c.nome?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            c.cpf_cnpj?.includes(searchTerm) ||
            c.processo?.toLowerCase().includes(searchTerm.toLowerCase());

        const matchesDate = selectedDate ? c.data_referencia === selectedDate : true;

        return matchesSearch && matchesDate;
    });

    if (!user) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black p-4">
                <div className="glass-panel w-full max-w-md p-8 rounded-2xl relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-red-600 to-transparent opacity-50"></div>

                    <div className="text-center mb-8">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-600/10 mb-4 border border-red-600/20">
                            <Database className="w-8 h-8 text-red-600" />
                        </div>
                        <h1 className="text-3xl font-bold text-white mb-2">WebBD</h1>
                        <p className="text-slate-400">Acesse o painel de dados extraídos</p>
                    </div>

                    <form onSubmit={handleLogin} className="space-y-6">
                        <div className="space-y-4">
                            <div className="relative">
                                <User className="absolute left-3 top-3.5 w-5 h-5 text-slate-500" />
                                <input
                                    type="text"
                                    placeholder="Usuário"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    className="input-field pl-12"
                                />
                            </div>
                        </div>

                        <div className="space-y-4">
                            <div className="relative">
                                <Lock className="absolute left-3 top-3.5 w-5 h-5 text-slate-500" />
                                <input
                                    type="password"
                                    placeholder="Senha"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="input-field pl-12"
                                />
                            </div>
                        </div>

                        {error && <p className="text-red-500 text-sm text-center">{error}</p>}

                        <button type="submit" className="btn-primary" disabled={loading}>
                            {loading ? 'Entrando...' : 'Acessar Sistema'}
                        </button>
                    </form>

                    <div className="mt-8 text-center text-xs text-slate-600">
                        &copy; 2026 WebBD v1.0
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-950 text-slate-200">
            {/* Navbar */}
            <nav className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-red-600 flex items-center justify-center">
                                <Database className="w-5 h-5 text-white" />
                            </div>
                            <span className="text-xl font-bold text-white tracking-tight">WebBD</span>
                        </div>

                        <div className="flex items-center gap-4">
                            <div className="text-sm text-slate-400 hidden sm:block">
                                Logado como <span className="text-white font-medium">{user.username || 'Admin'}</span>
                            </div>
                            <button onClick={logout} className="p-2 text-slate-400 hover:text-white transition-colors">
                                <LogOut className="w-5 h-5" />
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Stats / Search */}
                <div className="flex flex-col md:flex-row gap-6 mb-8 items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold text-white">Contratos Extraídos</h2>
                        <p className="text-slate-400">Gerenciamento e visualização de dados processados pela IA</p>
                    </div>

                    <div className="relative w-full md:w-96">
                        <Search className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                        <input
                            type="text"
                            placeholder="Buscar por nome, CPF ou processo..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="input-field pl-12"
                        />
                    </div>
                </div>

                {/* Filters and Actions */}
                <div className="flex flex-col md:flex-row gap-4 mb-6">
                    <div className="relative w-full md:w-64">
                        <Calendar className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                        <select
                            value={selectedDate}
                            onChange={(e) => setSelectedDate(e.target.value)}
                            className="input-field pl-12 appearance-none bg-slate-900 border-slate-700"
                        >
                            <option value="">Todas as datas</option>
                            {referenceDates.map(date => (
                                <option key={date} value={date}>{date}</option>
                            ))}
                        </select>
                    </div>

                    <button
                        onClick={handleExport}
                        disabled={exporting}
                        className="btn-primary flex items-center justify-center gap-2 md:w-auto w-full px-6"
                    >
                        <Download className="w-5 h-5" />
                        {exporting ? 'Exportando...' : 'Exportar CSV'}
                    </button>
                </div>

                {/* Data Grid */}
                <div className="glass-panel rounded-xl overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead>
                                <tr className="border-b border-slate-800 bg-slate-900/50">
                                    <th className="px-6 py-4 font-semibold text-slate-300">Processo</th>
                                    <th className="px-6 py-4 font-semibold text-slate-300">Data Ref.</th>
                                    <th className="px-6 py-4 font-semibold text-slate-300">Cliente (Emitente)</th>
                                    <th className="px-6 py-4 font-semibold text-slate-300">CPF/CNPJ</th>
                                    <th className="px-6 py-4 font-semibold text-slate-300">Contrato Ref.</th>
                                    <th className="px-6 py-4 font-semibold text-slate-300">Extração / Infos</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800">
                                {filteredContratos.map((c) => (
                                    <tr key={c.id} className="hover:bg-slate-900/30 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                <FileText className="w-4 h-4 text-slate-500" />
                                                <span className="font-mono text-sm">{c.processo}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-300">
                                                {c.data_referencia || 'N/A'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="font-medium text-white">{c.nome || 'Não identificado'}</div>
                                            <div className="text-sm text-slate-500 flex items-center gap-1 mt-1">
                                                <Mail className="w-3 h-3" /> {c.email || '-'}
                                            </div>
                                            <div className="text-sm text-slate-500 flex items-center gap-1 mt-0.5">
                                                <Smartphone className="w-3 h-3" /> {c.telefone || '-'}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-slate-300 font-mono text-sm">{c.cpf_cnpj || '-'}</td>
                                        <td className="px-6 py-4 text-slate-400 text-sm">{c.numero_contrato || '-'}</td>
                                        <td className="px-6 py-4 text-slate-500 text-xs">
                                            <div>{new Date(c.data_extracao).toLocaleString()}</div>
                                            {c.erro && (
                                                <div className="text-red-400 flex items-center gap-1 mt-1" title={c.erro}>
                                                    <AlertTriangle className="w-3 h-3" />
                                                    <span className="truncate max-w-[150px]">{c.erro}</span>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}

                                {filteredContratos.length === 0 && (
                                    <tr>
                                        <td colSpan="5" className="px-6 py-12 text-center text-slate-500">
                                            Nenhum registro encontrado.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main >
        </div >
    )
}

export default App
