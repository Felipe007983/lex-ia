const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');

const app = express();
const port = 3000;

app.use(cors());
app.use(express.json());

// Database Connection
const pool = new Pool({
    user: process.env.DB_USER || 'user',
    host: process.env.DB_HOST || 'db',
    database: process.env.DB_NAME || 'web_bd',
    password: process.env.DB_PASSWORD || 'password',
    port: 5432,
});

const JWT_SECRET = 'segredo_super_secreto_renner_123'; // Em prod, usar env var

// Middleware de Autenticação
const authenticateToken = (req, res, next) => {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    if (!token) return res.sendStatus(401);

    jwt.verify(token, JWT_SECRET, (err, user) => {
        if (err) return res.sendStatus(403);
        req.user = user;
        next();
    });
};

// Rotas de Autenticação
app.post('/login', async (req, res) => {
    const { username, password } = req.body;

    try {
        const result = await pool.query('SELECT * FROM users WHERE username = $1', [username]);

        if (result.rows.length === 0) {
            return res.status(401).json({ message: 'Usuário ou senha inválidos' });
        }

        const user = result.rows[0];

        // Verificar senha (simples ou hash)
        // Para simplificar o setup inicial, vamos aceitar texto plano se a senha no banco não for hash
        // Mas o ideal é sempre usar bcrypt.compare
        const validPassword = await bcrypt.compare(password, user.password_hash);

        if (!validPassword) {
            return res.status(401).json({ message: 'Usuário ou senha inválidos' });
        }

        const accessToken = jwt.sign({ username: user.username, role: 'admin' }, JWT_SECRET, { expiresIn: '8h' });
        res.json({ token: accessToken });

    } catch (err) {
        console.error(err);
        res.status(500).json({ message: 'Erro interno no servidor' });
    }
});

// Rotas de Dados (Protegidas)
app.get('/api/contratos', authenticateToken, async (req, res) => {
    try {
        const result = await pool.query('SELECT * FROM contratos_extraidos ORDER BY data_extracao DESC');
        res.json(result.rows);
    } catch (err) {
        console.error(err);
        res.status(500).json({ message: 'Erro ao buscar dados' });
    }
});

// Endpoint para buscar datas de referência únicas
app.get('/api/dates', authenticateToken, async (req, res) => {
    try {
        const result = await pool.query('SELECT DISTINCT data_referencia FROM contratos_extraidos WHERE data_referencia IS NOT NULL ORDER BY data_referencia DESC');
        const dates = result.rows.map(row => row.data_referencia);
        res.json(dates);
    } catch (err) {
        console.error(err);
        res.status(500).json({ message: 'Erro ao buscar datas' });
    }
});

// Endpoint para exportar CSV (filtrado por data ou tudo)
app.get('/api/export', authenticateToken, async (req, res) => {
    try {
        const { date } = req.query;
        let query = 'SELECT * FROM contratos_extraidos';
        let params = [];

        if (date) {
            query += ' WHERE data_referencia = $1';
            params.push(date);
        }

        query += ' ORDER BY data_extracao DESC';

        const result = await pool.query(query, params);

        // Simples conversão para CSV
        if (result.rows.length === 0) {
            return res.status(404).json({ message: 'Nenhum dado encontrado para exportar.' });
        }

        const fields = Object.keys(result.rows[0]);
        const csv = [
            fields.join(','), // Header
            ...result.rows.map(row => fields.map(field => {
                let val = row[field] === null ? '' : row[field];
                // Escapar aspas e quebras de linha
                val = String(val).replace(/"/g, '""');
                return `"${val}"`;
            }).join(','))
        ].join('\n');

        res.header('Content-Type', 'text/csv');
        res.attachment(`contratos_${date || 'todos'}.csv`);
        res.send(csv);

    } catch (err) {
        console.error(err);
        res.status(500).json({ message: 'Erro ao exportar dados' });
    }
});

app.get('/health', (req, res) => {
    res.json({ status: 'OK', timestamp: new Date() });
});

app.listen(port, () => {
    console.log(`Backend rodando na porta ${port}`);
});
